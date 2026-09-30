"""The harness: a queue agent works the run, and a claim agent works each claim."""

import json
import logging
import os
import uuid
from collections.abc import Callable
from functools import partial
from typing import Any, cast

from langchain.agents import AgentState, create_agent
from langchain.agents.middleware import (
    AgentMiddleware,
    InputAgentState,
    ModelCallLimitMiddleware,
    ToolCallRequest,
    ToolErrorMiddleware,
)
from langchain.tools import ToolException
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph.state import CompiledStateGraph
from langgraph.runtime import Runtime
from langgraph.types import Command
from pydantic import SecretStr

from agent import api
from agent.tools import CLAIM_TOOLS, QUEUE_TOOLS, ClaimContext, RunContext

log = logging.getLogger(__name__)

ClaimAgent = CompiledStateGraph[Any, ClaimContext, Any, Any]
QueueAgent = CompiledStateGraph[Any, RunContext, Any, Any]

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "deepseek/deepseek-v4.1-flash"
CLAIM_MODEL_CALLS = 30
QUEUE_MODEL_CALLS_PER_CLAIM = 6
QUEUE_MODEL_CALLS_TO_PLAN = 12
REMINDERS = 2
NO_DECISION = "The agent finished without recording a decision"
NO_SUMMARY = "The run finished without a summary."
STOPPED = "The run stopped before this claim was finished"


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


def refusal(error: Exception, request: ToolCallRequest) -> str | None:
    """Show the model why a tool was refused; let any other error stop the agent."""
    if isinstance(error, api.Refused):
        return f"Refused with status {error}"
    if isinstance(error, ToolException):
        return f"Refused: {error}"
    return None


class RecordSteps(AgentMiddleware[AgentState, ClaimContext]):
    """Record each step of a claim agent's work on its claim, for the dashboard,
    including any step a tool gives as its artifact, such as a section it read."""

    def after_model(
        self, state: AgentState, runtime: Runtime[ClaimContext]
    ) -> dict[str, Any] | None:
        claim_id = runtime.context.claim_id
        message = state["messages"][-1]
        if message.text:
            api.record_step(claim_id, "message", message.text)
        if isinstance(message, AIMessage):
            for call in message.tool_calls:
                args = ", ".join(
                    f"{k}={json.dumps(v)}" for k, v in call["args"].items()
                )
                api.record_step(claim_id, "tool_call", f"{call['name']}({args})")

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command],
    ) -> ToolMessage | Command:
        result = handler(request)
        if isinstance(result, ToolMessage):
            claim_id = cast(ClaimContext, request.runtime.context).claim_id
            api.record_step(claim_id, "tool_result", f"{result.name}: {result.text}")
            if result.artifact:
                api.record_step(claim_id, *result.artifact)
        return result


def ask(text: str) -> InputAgentState:
    """Give an agent one message from the user."""
    return {"messages": [HumanMessage(text)]}


def describe(error: Exception) -> str:
    """Say in one line what went wrong."""
    lines = str(error).splitlines()
    return f"{type(error).__name__}: {lines[0]}" if lines else type(error).__name__


def report(claim: dict[str, Any], reason: str) -> str:
    """Say in one line how a claim ended: its decision and payout, or why it failed."""
    claim_id, status, decision = claim["claim_id"], claim["status"], claim["decision"]
    if status == "waiting":
        return f"{claim_id}  failed: {reason}, back in the queue"
    if status == "left_for_handler":
        return f"{claim_id}  failed: {reason}, left for a handler"
    line = f"{claim_id}  {decision['decision']}  ${decision['payout']:,.2f}"
    if status == "waiting_for_sign_off":
        return f"{line}, waiting for sign-off"
    if decision["decision"] == "approve" and claim["payment"] is None:
        return f"{line}, not paid"
    return line


def claim_agent(llm: BaseChatModel) -> ClaimAgent:
    """Build the claim agent, which works one claim from a clean start each time."""
    middleware: list[AgentMiddleware[Any, Any]] = [
        ModelCallLimitMiddleware(run_limit=CLAIM_MODEL_CALLS, exit_behavior="error"),
        RecordSteps(),
        ToolErrorMiddleware(refusal),
    ]
    return create_agent(
        llm,
        tools=CLAIM_TOOLS,
        system_prompt=api.get_instructions()["claim"],
        middleware=middleware,
        context_schema=ClaimContext,
        checkpointer=False,
    )


def work_claim(claim_id: str, agent: ClaimAgent) -> str:
    """Work one claim from a clean start, as a new attempt, and report how it ended."""
    api.start_claim(claim_id, str(uuid.uuid4()))
    reason = NO_DECISION
    try:
        agent.invoke(ask(f"Claim {claim_id}"), context=ClaimContext(claim_id))
    except Exception as error:  # a claim that fails must not stop the run
        reason = describe(error)
    claim = api.get_claim(claim_id)
    if claim["status"] == "in_progress":
        claim = api.fail_claim(claim_id, reason)
    line = report(claim, reason)
    log.info(line)
    return line


def waiting() -> list[str]:
    """Return the ids of the claims waiting in the queue, oldest submitted first."""
    claims = sorted(api.list_claims(), key=lambda claim: claim["submitted_on"])
    return [claim["claim_id"] for claim in claims if claim["status"] == "waiting"]


def recover() -> None:
    """Put back in the queue any claim left in progress by a run that stopped."""
    for claim in api.list_claims():
        if claim["status"] == "in_progress":
            api.fail_claim(claim["claim_id"], STOPPED)


def missed(run: RunContext) -> list[str]:
    """Return the waiting claims the run should still work: its own, then new ones."""
    ids = waiting()
    own = [claim_id for claim_id in ids if claim_id in run.started]
    new = [claim_id for claim_id in ids if claim_id not in run.started]
    return own + new[: run.cap - len(run.started)]


def queue_agent(llm: BaseChatModel, cap: int) -> QueueAgent:
    """Build the queue agent for a run, which keeps its conversation between turns."""
    calls = QUEUE_MODEL_CALLS_PER_CLAIM * cap + QUEUE_MODEL_CALLS_TO_PLAN
    middleware: list[AgentMiddleware[Any, Any]] = [
        ModelCallLimitMiddleware(run_limit=calls, exit_behavior="error"),
        ToolErrorMiddleware(refusal),
    ]
    return create_agent(
        llm,
        tools=QUEUE_TOOLS,
        system_prompt=api.get_instructions()["queue"],
        middleware=middleware,
        context_schema=RunContext,
        checkpointer=InMemorySaver(),
    )


def work_queue(run: RunContext, agent: QueueAgent) -> str:
    """Let the queue agent work the run, naming any claims it missed, and summarize."""
    # One tool call at a time, so the cap holds when several claims are handed over.
    config: RunnableConfig = {
        "configurable": {"thread_id": run.run_id},
        "max_concurrency": 1,
    }
    message = f"Please work the queue. This run can work up to {run.cap} claims."
    state = agent.invoke(ask(message), config, context=run)
    for _ in range(REMINDERS):
        left = missed(run)
        if not left:
            break
        reminder = (
            "These claims are still waiting within the run's cap: "
            f"{', '.join(left)}. Please work them, then finish with the summary."
        )
        state = agent.invoke(ask(reminder), config, context=run)
    return state["messages"][-1].text or NO_SUMMARY


def run_queue(cap: int | None, llm: BaseChatModel, claim_llm: BaseChatModel) -> None:
    """Work the queue with a queue agent, up to cap claims or every waiting claim."""
    recover()
    count = len(waiting())
    if count == 0:
        log.info("No claims are waiting")
        return
    cap = min(cap or count, count)
    run_id = api.start_run(cap)["run_id"]
    run = RunContext(run_id, cap, partial(work_claim, agent=claim_agent(claim_llm)))
    try:
        summary = work_queue(run, queue_agent(llm, cap))
    except Exception as error:
        api.finish_run(run_id, f"The run stopped: {describe(error)}")
        raise
    api.finish_run(run_id, summary)
    log.info(summary)
