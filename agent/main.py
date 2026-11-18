"""The UnderCover Agent."""

import json
import os
from collections.abc import Iterable, Iterator
from typing import Literal
from urllib.parse import quote

import httpx
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain.agents.middleware import (
    ModelCallLimitMiddleware,
    ModelRetryMiddleware,
)
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AnyMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

load_dotenv(override=True)

BACKEND_URL = "http://localhost:8000"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "deepseek/deepseek-v4.1-flash"
RETRY_DELAY = 1.0
CALL_LIMIT = 30
DOCUMENT_NAMES = {"policy-wording": "Policy wording", "claims-manual": "Claims manual"}
MAX_RESULT_CHARS = 400


class ClaimError(Exception):
    """The backend refused to start work on a claim."""


def backend() -> httpx.Client:
    """Return a client for the UnderCover backend."""
    return httpx.Client(base_url=BACKEND_URL, timeout=30)


def call(method: str, path: str, body: dict | None = None) -> str:
    """Call the backend and return the reply, or the refusal as text."""
    with backend() as client:
        response = client.request(method, path, json=body)
    if response.is_error:
        return f"Error {response.status_code}: {response.text}"
    return response.text


@tool
def get_claim(claim_id: str) -> str:
    """Get a claim: the story, items, documents, status and any decision."""
    return call("GET", f"/api/claims/{claim_id}")


@tool
def get_policy(policy_id: str) -> str:
    """Get a policy: its plan, add-ons, purchase date, trip and travelers."""
    return call("GET", f"/api/policies/{policy_id}")


@tool
def get_customer(customer_id: str) -> str:
    """Get a customer's name and claim history."""
    return call("GET", f"/api/customers/{customer_id}")


@tool
def get_plan(plan: str) -> str:
    """Get a plan's limits, waiting periods and deductible, by plan name."""
    return call("GET", f"/api/plans/{plan}")


@tool
def list_sections(document: Literal["policy-wording", "claims-manual"]) -> str:
    """List the numbered sections of the policy wording or the claims manual."""
    return call("GET", f"/api/documents/{document}/sections")


@tool
def search_sections(query: str) -> str:
    """Find the sections of the wording and the manual that contain every word."""
    return call("GET", f"/api/sections?query={quote(query)}")


@tool
def read_section(
    document: Literal["policy-wording", "claims-manual"], number: int
) -> str:
    """Read one numbered section of the policy wording or the claims manual."""
    return call("GET", f"/api/documents/{document}/sections/{number}")


@tool
def decide_claim(
    claim_id: str,
    decision: Literal["approve", "decline", "refer"],
    payout: float,
    explanation: str,
    policy_section: str,
) -> str:
    """Record the decision on a claim. The payout is 0 unless you approve."""
    body = {
        "decision": decision,
        "payout": payout,
        "explanation": explanation,
        "policy_section": policy_section,
    }
    return call("POST", f"/api/claims/{claim_id}/decision", body)


@tool
def pay_claim(claim_id: str, amount: float) -> str:
    """Pay an approved claim its payout. Payouts over $1,000 wait for sign-off."""
    return call("POST", f"/api/claims/{claim_id}/payment", {"amount": amount})


TOOLS = [
    get_claim,
    get_policy,
    get_customer,
    get_plan,
    list_sections,
    search_sections,
    read_section,
    decide_claim,
    pay_claim,
]


def model() -> ChatOpenAI:
    """Return the model named in MODEL_NAME, or DeepSeek V4.1 Flash by default."""
    name = os.getenv("MODEL_NAME")
    return ChatOpenAI(
        model=name or DEFAULT_MODEL,
        base_url=OPENROUTER_BASE_URL,
        api_key=SecretStr(os.environ["OPENROUTER_API_KEY"]),
        reasoning_effort=None if name else "low",
    )


def middleware(call_limit: int | None = None):
    """Retry a failed model call, and stop an agent that keeps calling the model."""
    return [
        ModelRetryMiddleware(
            max_retries=2, on_failure="error", initial_delay=RETRY_DELAY
        ),
        ModelCallLimitMiddleware(
            run_limit=call_limit or CALL_LIMIT, exit_behavior="error"
        ),
    ]


def steps_from(message: AnyMessage) -> list[tuple[str, str]]:
    """Turn one message of the agent's work into steps for the dashboard."""
    if isinstance(message, ToolMessage):
        text = str(message.content)
        if message.name == "read_section" and not text.startswith("Error"):
            section = json.loads(text)
            name = DOCUMENT_NAMES[section["document"]]
            return [("read", f"{name}, {section['number']}. {section['title']}")]
        if len(text) > MAX_RESULT_CHARS:
            text = text[:MAX_RESULT_CHARS] + "..."
        return [("tool_result", f"{message.name}: {text}")]
    if not isinstance(message, AIMessage):
        return []
    steps = []
    if message.text:
        steps.append(("message", message.text))
    for tool_call in message.tool_calls:
        arguments = ", ".join(f"{k}={v!r}" for k, v in tool_call["args"].items())
        steps.append(("tool_call", f"{tool_call['name']}({arguments})"))
    return steps


def messages_in(updates: Iterable[dict]) -> Iterator[AnyMessage]:
    """Yield the messages of the agent's stream, skipping steps that add none."""
    for update in updates:
        for node in update.values():
            yield from (node or {}).get("messages", [])


def run(claim_id: str, thread_id: str, llm: BaseChatModel | None = None) -> str:
    """Run the agent on one claim and return its final reply."""
    with backend() as client:
        started = client.post(f"/api/claims/{claim_id}/start")
        if started.is_error:
            raise ClaimError(f"{claim_id}: {started.json()['detail']}")
        instructions = client.get("/api/instructions/claim").text
        agent = create_agent(
            llm or model(),
            tools=TOOLS,
            system_prompt=instructions,
            middleware=middleware(),
        )
        reply = ""
        for message in messages_in(
            agent.stream(
                {"messages": [{"role": "user", "content": f"Claim {claim_id}"}]},
                config={"configurable": {"thread_id": thread_id}},
                stream_mode="updates",
            )
        ):
            for kind, text in steps_from(message):
                client.post(
                    f"/api/claims/{claim_id}/steps",
                    json={"kind": kind, "text": text},
                ).raise_for_status()
            if isinstance(message, AIMessage):
                reply = message.text
    return reply
