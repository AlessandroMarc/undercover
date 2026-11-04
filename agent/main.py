"""The UnderCover Agent."""

import os
from typing import Literal

import httpx
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AnyMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

load_dotenv(override=True)

BACKEND_URL = "http://localhost:8000"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "openai/gpt-6-luna"
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
def get_policy_wording() -> str:
    """Get the policy wording, the contract with the customer."""
    return call("GET", "/api/policy-wording")


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
    get_policy_wording,
    decide_claim,
    pay_claim,
]


def model() -> ChatOpenAI:
    """Return the model named in MODEL_NAME, or GPT-6 Luna by default."""
    name = os.getenv("MODEL_NAME")
    return ChatOpenAI(
        model=name or DEFAULT_MODEL,
        base_url=OPENROUTER_BASE_URL,
        api_key=SecretStr(os.environ["OPENROUTER_API_KEY"]),
        reasoning_effort=None if name else "low",
    )


def steps_from(message: AnyMessage) -> list[tuple[str, str]]:
    """Turn one message of the agent's work into steps for the dashboard."""
    if isinstance(message, ToolMessage):
        text = str(message.content)
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


def run(claim_id: str, thread_id: str, llm: BaseChatModel | None = None) -> str:
    """Run the agent on one claim and return its final reply."""
    with backend() as client:
        started = client.post(f"/api/claims/{claim_id}/start")
        if started.is_error:
            raise ClaimError(f"{claim_id}: {started.json()['detail']}")
        instructions = client.get("/api/instructions").text
        agent = create_agent(llm or model(), tools=TOOLS, system_prompt=instructions)
        reply = ""
        for update in agent.stream(
            {"messages": [{"role": "user", "content": f"Claim {claim_id}"}]},
            config={"configurable": {"thread_id": thread_id}},
            stream_mode="updates",
        ):
            for node in update.values():
                for message in node["messages"]:
                    for kind, text in steps_from(message):
                        client.post(
                            f"/api/claims/{claim_id}/steps",
                            json={"kind": kind, "text": text},
                        ).raise_for_status()
                    if isinstance(message, AIMessage):
                        reply = message.text
    return reply
