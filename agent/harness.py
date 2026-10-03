"""The harness: a queue agent works the run, and a claim graph works each claim."""

import contextvars
import json
import logging
import os
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from functools import partial
from typing import Any, cast

from langchain.agents import create_agent
from langchain.agents.middleware import (
    AgentMiddleware,
    InputAgentState,
    ModelCallLimitMiddleware,
    ToolCallRequest,
    ToolErrorMiddleware,
)
from langchain.tools import ToolException
from langchain_core.language_models import BaseChatModel, LanguageModelInput
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.runnables import Runnable, RunnableConfig
from langchain_openai import ChatOpenAI
from langfuse.langchain import CallbackHandler
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode
from langgraph.runtime import Runtime
from langgraph.types import Command, interrupt
from psycopg import Connection, sql
from psycopg.rows import DictRow, dict_row
from psycopg_pool import ConnectionPool
from pydantic import SecretStr

from agent import api
from agent.tools import CLAIM_TOOLS, QUEUE_TOOLS, ClaimContext, ClaimState, RunContext

log = logging.getLogger(__name__)

ClaimGraph = CompiledStateGraph[ClaimState, ClaimContext, Any, Any]
QueueAgent = CompiledStateGraph[Any, RunContext, Any, Any]

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "deepseek/deepseek-v4.1-flash"
SCHEMA = "undercover"
CONNECTIONS = 4
CLAIM_MODEL_CALLS = 30
QUEUE_MODEL_CALLS_PER_CLAIM = 6
QUEUE_MODEL_CALLS_TO_PLAN = 12
REMINDERS = 2
NO_DECISION = "The agent finished without recording a decision"
NO_SUMMARY = "The run finished without a summary."
STOPPED = "The run stopped before this claim was finished"
WORK_CLAIM = "Work claim"


class TooManyModelCalls(Exception):
    """The claim agent made as many model calls as it may without finishing."""


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


@contextmanager
def checkpointer() -> Iterator[PostgresSaver]:
    """Save the claim graph's progress in Postgres at DATABASE_URL, in our own schema,
    with at most CONNECTIONS connections."""
    settings = {
        "autocommit": True,
        "prepare_threshold": 0,
        "row_factory": dict_row,
        "options": f"-c search_path={SCHEMA}",
    }
    with ConnectionPool[Connection[DictRow]](
        os.environ["DATABASE_URL"],
        min_size=1,
        max_size=CONNECTIONS,
        kwargs=settings,
    ) as pool:
        with pool.connection() as connection:
            create = sql.SQL("CREATE SCHEMA IF NOT EXISTS {}")
            connection.execute(create.format(sql.Identifier(SCHEMA)))
        saver = PostgresSaver(pool)
        saver.setup()
        yield saver


def refusal(error: Exception) -> str:
    """Show the model why a tool was refused, and let any other error stop the agent."""
    if isinstance(error, api.Refused):
        return f"Refused with status {error}"
    if isinstance(error, ToolException):
        return f"Refused: {error}"
    raise error


def record_reply(claim_id: str, reply: BaseMessage) -> None:
    """Record the model's reply on the claim: its text, then each tool it calls."""
    if reply.text:
        api.record_step(claim_id, "message", reply.text)
    if isinstance(reply, AIMessage):
        for call in reply.tool_calls:
            args = ", ".join(f"{k}={json.dumps(v)}" for k, v in call["args"].items())
            api.record_step(claim_id, "tool_call", f"{call['name']}({args})")


def record_result(
    request: ToolCallRequest,
    execute: Callable[[ToolCallRequest], ToolMessage | Command],
) -> ToolMessage | Command:
    """Run a tool and record its result on the claim, then any step it gives as its
    artifact, such as a section it read."""
    result = execute(request)
    if isinstance(result, ToolMessage):
        message = result
    else:
        message = cast(dict[str, Any], result.update)["messages"][0]
    claim_id = cast(ClaimContext, request.runtime.context).claim_id
    api.record_step(claim_id, "tool_result", f"{message.name}: {message.text}")
    if message.artifact:
        api.record_step(claim_id, *message.artifact)
    return result


def call_model(
    state: ClaimState,
    runtime: Runtime[ClaimContext],
    llm: Runnable[LanguageModelInput, BaseMessage],
    instructions: SystemMessage,
) -> dict[str, Any]:
    """Ask the model for its next step, up to CLAIM_MODEL_CALLS times in all, and
    record its reply on the claim."""
    calls = state["model_calls"]
    if calls >= CLAIM_MODEL_CALLS:
        message = f"The claim agent made {calls} model calls without finishing"
        raise TooManyModelCalls(message)
    reply = llm.invoke([instructions, *state["messages"]])
    record_reply(runtime.context.claim_id, reply)
    return {"messages": [reply], "model_calls": 1}


def wait_for_sign_off(state: ClaimState, runtime: Runtime[ClaimContext]) -> None:
    """Pause until a handler signs off the payout. On resume this runs again from the
    top, so nothing comes before the interrupt."""
    interrupt({"claim_id": runtime.context.claim_id})


def pay(state: ClaimState, runtime: Runtime[ClaimContext]) -> dict[str, Any]:
    """Pay the approved payout, which the backend refuses unless it may be paid."""
    claim = api.pay_claim(runtime.context.claim_id, state["decision"]["payout"])
    return {"status": claim["status"]}


def after_agent(state: ClaimState) -> str:
    """Run the tools the model asked for, or stop: it finished without a decision."""
    reply = state["messages"][-1]
    return "tools" if isinstance(reply, AIMessage) and reply.tool_calls else END


def after_tools(state: ClaimState) -> str:
    """Go back to the model until a decision is recorded, then pay an approval, after
    a sign-off if the backend holds it, or stop."""
    decision, status = state["decision"], state["status"]
    if not decision:
        return "agent"
    if status == api.Status.WAITING_FOR_SIGN_OFF:
        return "wait_for_sign_off"
    if decision["decision"] == api.APPROVE and status == api.Status.IN_PROGRESS:
        return "pay"
    return END


def claim_graph(llm: BaseChatModel, saver: BaseCheckpointSaver[Any]) -> ClaimGraph:
    """Build the claim agent's graph, which saves its progress after every step."""
    instructions = SystemMessage(api.get_instructions()["claim"])
    builder = StateGraph(ClaimState, context_schema=ClaimContext)
    builder.add_node(
        "agent",
        partial(call_model, llm=llm.bind_tools(CLAIM_TOOLS), instructions=instructions),
    )
    builder.add_node(
        "tools",
        ToolNode(CLAIM_TOOLS, handle_tool_errors=refusal, wrap_tool_call=record_result),
    )
    builder.add_node("wait_for_sign_off", wait_for_sign_off)
    builder.add_node("pay", pay)
    builder.add_edge(START, "agent")
    builder.add_conditional_edges("agent", after_agent, ["tools", END])
    builder.add_conditional_edges(
        "tools", after_tools, ["agent", "wait_for_sign_off", "pay", END]
    )
    builder.add_edge("wait_for_sign_off", "pay")
    builder.add_edge("pay", END)
    return builder.compile(checkpointer=saver)


def claim_config(claim: dict[str, Any], name: str) -> RunnableConfig:
    """Run on the claim's thread, traced in Langfuse in the session of that thread."""
    session = f"{claim['claim_id']}:{claim['thread_id']}"
    return {
        "configurable": {"thread_id": claim["thread_id"]},
        "callbacks": [CallbackHandler()],
        "metadata": {"langfuse_session_id": session, "langfuse_trace_name": name},
        # One tool call at a time, so two decisions in one reply can't race.
        "max_concurrency": 1,
    }


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
    if status == api.Status.WAITING:
        return f"{claim_id}  failed: {reason}, back in the queue"
    if status == api.Status.LEFT_FOR_HANDLER:
        return f"{claim_id}  failed: {reason}, left for a handler"
    line = f"{claim_id}  {decision['decision']}  ${decision['payout']:,.2f}"
    if status == api.Status.WAITING_FOR_SIGN_OFF:
        return f"{line}, waiting for sign-off"
    if decision["decision"] == api.APPROVE and claim["payment"] is None:
        return f"{line}, not paid yet"
    return line


def undecided(claim: dict[str, Any]) -> bool:
    """Say whether a claim is in progress without a decision."""
    return claim["status"] == api.Status.IN_PROGRESS and claim["decision"] is None


def run_claim_graph(
    graph: ClaimGraph, start: InputAgentState, claim: dict[str, Any], name: str
) -> str | None:
    """Run the claim graph on the claim's thread, saving each step, and say what went
    wrong, if anything."""
    try:
        # A fresh context makes this a root run even inside the queue agent's tool,
        # which Langfuse needs to put it in the claim's session.
        contextvars.Context().run(
            graph.invoke,
            start,
            claim_config(claim, name),
            context=ClaimContext(claim["claim_id"]),
            durability="sync",
        )
    except Exception as error:  # a claim that fails must not stop the run
        return describe(error)
    return None


def settle(claim_id: str, error: str | None) -> str:
    """Fail a claim the agent left undecided, and report how the claim ended. An
    error after the decision is logged, and the claim keeps its decision."""
    claim = api.get_claim(claim_id)
    reason = error or NO_DECISION
    if undecided(claim):
        claim = api.fail_claim(claim_id, reason)
    elif error:
        log.warning("%s  %s", claim_id, error)
    line = report(claim, reason)
    log.info(line)
    return line


def work_claim(claim_id: str, graph: ClaimGraph) -> str:
    """Work one claim from a clean start, as a new attempt, and report how it ended."""
    claim = api.start_claim(claim_id, str(uuid.uuid4()))
    error = run_claim_graph(graph, ask(f"Claim {claim_id}"), claim, WORK_CLAIM)
    return settle(claim_id, error)


def waiting() -> list[str]:
    """Return the ids of the claims waiting in the queue, oldest submitted first."""
    claims = sorted(api.list_claims(), key=lambda claim: claim["submitted_on"])
    return [c["claim_id"] for c in claims if c["status"] == api.Status.WAITING]


def recover() -> None:
    """Put back in the queue any undecided claim left in progress by a run that
    stopped."""
    for claim in api.list_claims():
        if undecided(claim):
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
        ToolErrorMiddleware(lambda error, _: refusal(error)),
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


def run_queue(cap: int | None, llm: BaseChatModel, graph: ClaimGraph) -> None:
    """Work the queue with a queue agent, up to cap claims or every waiting claim."""
    recover()
    count = len(waiting())
    if count == 0:
        log.info("No claims are waiting")
        return
    cap = min(cap or count, count)
    run_id = api.start_run(cap)["run_id"]
    run = RunContext(run_id, cap, partial(work_claim, graph=graph))
    try:
        summary = work_queue(run, queue_agent(llm, cap))
    except Exception as error:
        api.finish_run(run_id, f"The run stopped: {describe(error)}")
        raise
    api.finish_run(run_id, summary)
    log.info(summary)
