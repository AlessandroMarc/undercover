"""The UnderCover Agent."""

import json
import os
import uuid
from typing import Any

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AnyMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import SecretStr

from agent.tools import CLAIM_TOOLS, REFUSED, request

load_dotenv(override=True)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "deepseek/deepseek-v4.1-flash"
STEPS = 60


def model() -> ChatOpenAI:
    """Return the model named in MODEL_NAME, or DeepSeek V4.1 Flash by default."""
    name = os.getenv("MODEL_NAME")
    return ChatOpenAI(
        model=name or DEFAULT_MODEL,
        base_url=OPENROUTER_BASE_URL,
        api_key=SecretStr(os.environ["OPENROUTER_API_KEY"]),
        reasoning_effort=None if name else "low",
        timeout=120,
        max_retries=5,
    )


class BackendError(Exception):
    """The backend refused a request the agent's run depends on."""


def call_backend(method: str, path: str, body: dict[str, Any] | None = None) -> Any:
    """Call the backend and return its JSON, raising if it refuses."""
    response = request(method, path, body)
    if response.is_error:
        raise BackendError(f"{response.status_code}: {response.json()['detail']}")
    return response.json()


def reading(result: str) -> list[tuple[str, str]]:
    """Name a section the agent read, like "Claims manual, section 9: Repeat claims"."""
    if result.startswith(REFUSED):
        return []
    section = json.loads(result)
    document = section["document"].replace("_", " ").capitalize()
    return [("reading", f"{document}, section {section['number']}: {section['title']}")]


def steps(message: AnyMessage) -> list[tuple[str, str]]:
    """Turn one message from the agent's run into steps for the dashboard."""
    if isinstance(message, ToolMessage):
        found = [("tool_result", f"{message.name}: {message.text}")]
        if message.name == "read_section" and message.status == "success":
            found += reading(message.text)
        return found
    found = []
    if message.text:
        found.append(("message", message.text))
    if isinstance(message, AIMessage):
        for call in message.tool_calls:
            args = ", ".join(f"{k}={json.dumps(v)}" for k, v in call["args"].items())
            found.append(("tool_call", f"{call['name']}({args})"))
    return found


def work(claim_id: str, thread_id: str, llm: BaseChatModel | None) -> None:
    """Run a claim agent on a started claim, recording each step with the backend."""
    instructions = call_backend("GET", "/api/instructions")["claim"]
    agent = create_agent(
        llm or model(),
        tools=CLAIM_TOOLS,
        system_prompt=instructions,
        checkpointer=InMemorySaver(),
    )
    states = agent.stream(
        {"messages": [{"role": "user", "content": f"Claim {claim_id}"}]},
        config={"configurable": {"thread_id": thread_id}, "recursion_limit": STEPS},
        stream_mode="values",
    )
    messages = next(states)["messages"]
    for state in states:
        for message in state["messages"][len(messages) :]:
            for kind, content in steps(message):
                call_backend(
                    "POST",
                    f"/api/claims/{claim_id}/steps",
                    {"kind": kind, "content": content},
                )
        messages = state["messages"]


def describe(error: Exception) -> str:
    """Say in one line what went wrong."""
    lines = str(error).splitlines()
    return f"{type(error).__name__}: {lines[0]}" if lines else type(error).__name__


def report(claim: dict[str, Any]) -> str:
    """Give a claim's decision and payout in one line, like the handlers' queue."""
    decision = claim["decision"]
    line = f"{claim['claim_id']}  {decision['decision']}  ${decision['payout']:,.2f}"
    if claim["status"] == "waiting_for_sign_off":
        return f"{line}, waiting for sign-off"
    if decision["decision"] == "approve" and claim["payment"] is None:
        return f"{line}, not paid"
    return line


def work_claim(claim_id: str, llm: BaseChatModel | None = None) -> str:
    """Work one claim with a new claim agent, and report back in one line."""
    thread_id = str(uuid.uuid4())
    try:
        call_backend("POST", f"/api/claims/{claim_id}/start", {"thread_id": thread_id})
    except BackendError as error:
        return f"{claim_id}  not started: {error}"
    reason = "The agent finished without recording a decision"
    try:
        work(claim_id, thread_id, llm)
    except Exception as error:  # a claim that fails must not stop the run
        reason = describe(error)
    claim = call_backend("GET", f"/api/claims/{claim_id}")
    if claim["status"] != "in_progress":
        return report(claim)
    claim = call_backend("POST", f"/api/claims/{claim_id}/failure", {"reason": reason})
    if claim["status"] == "left_for_handler":
        return f"{claim_id}  failed: {reason}, left for a handler"
    return f"{claim_id}  failed: {reason}, back in the queue"


def work_queue() -> None:
    """Work every waiting claim in queue order, printing each report."""
    for claim in call_backend("GET", "/api/claims"):
        if claim["status"] == "waiting":
            print(work_claim(claim["claim_id"]), flush=True)
