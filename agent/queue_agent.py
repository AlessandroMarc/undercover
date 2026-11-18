"""The queue agent: plans the work, hands each claim to a fresh claim agent, reports."""

from dataclasses import dataclass, field
from typing import Literal

from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import tool
from pydantic import BaseModel

from agent import main as core
from agent.harness import work_claim
from agent.main import ClaimError, messages_in, steps_from

QUEUE_CALL_LIMIT = 200
LEFT_OPEN = ("waiting", "in_progress")


class RunFailed(Exception):
    """The run stopped before it finished."""


class TodoItem(BaseModel):
    content: str
    status: Literal["todo", "in_progress", "done", "left_for_handler"]


@dataclass
class QueueRun:
    """The state of one run: its id, its cap and the claims it has taken."""

    run_id: int
    cap: int
    llm: BaseChatModel
    taken: list[str] = field(default_factory=list)
    finished: bool = False


def statuses() -> dict[str, str]:
    with core.backend() as client:
        claims = client.get("/api/claims").json()
    return {claim["claim_id"]: claim["status"] for claim in claims}


def missed_claims(run: QueueRun) -> str:
    """Say what the run has missed, or return nothing if it may finish."""
    current = statuses()
    back = [claim for claim in run.taken if current[claim] in LEFT_OPEN]
    if back:
        return f"{', '.join(back)} still waiting or in progress. Work them first."
    others = [c for c, s in current.items() if s == "waiting" and c not in run.taken]
    if len(run.taken) < run.cap and others:
        return (
            f"You have taken {len(run.taken)} of your {run.cap} claims, and these "
            f"are still waiting: {', '.join(others[:10])}. Work them first."
        )
    return ""


def queue_tools(run: QueueRun) -> list:
    """The tools of one run of the queue agent."""

    @tool
    def list_waiting_claims() -> str:
        """List the claims still waiting: id, type, amount claimed and a summary."""
        with core.backend() as client:
            claims = client.get("/api/claims").json()
        lines = [
            f"{c['claim_id']} | {c['claim_type']} | ${c['amount_claimed']:,.2f}"
            f" | {c['summary']}"
            for c in claims
            if c["status"] == "waiting"
        ]
        return "\n".join(lines) or "No claims are waiting."

    @tool("work_claim")
    def work_claim_tool(claim_id: str) -> str:
        """Hand one waiting claim to a fresh claim agent. Returns a one-line report."""
        if claim_id not in run.taken and len(run.taken) >= run.cap:
            return f"Error: your cap of {run.cap} claims is used up. Do not take more."
        if statuses().get(claim_id) != "waiting":
            return f"Error: {claim_id} is not waiting."
        if claim_id not in run.taken:
            run.taken.append(claim_id)
        try:
            return work_claim(claim_id, run.llm)
        except ClaimError as error:
            return f"Error: {error}"

    @tool
    def write_todos(todos: list[TodoItem]) -> str:
        """Write the whole to-do list for this run, replacing the last one."""
        body = {"todos": [todo.model_dump() for todo in todos]}
        with core.backend() as client:
            client.put(f"/api/runs/{run.run_id}/todos", json=body).raise_for_status()
        return "To-do list saved."

    @tool
    def finish_run(summary: str) -> str:
        """End the run with a short summary for the handlers, if no claim was missed."""
        missed = missed_claims(run)
        if missed:
            return f"Not finished. {missed}"
        close(run.run_id, "finished", summary)
        run.finished = True
        return "Run finished."

    return [list_waiting_claims, work_claim_tool, write_todos, finish_run]


def close(run_id: int, status: str, summary: str) -> None:
    with core.backend() as client:
        client.post(
            f"/api/runs/{run_id}/finish", json={"status": status, "summary": summary}
        ).raise_for_status()


def release_stuck(run: QueueRun) -> None:
    """Send any claim this run left in progress back to the queue."""
    current = statuses()
    with core.backend() as client:
        for claim in run.taken:
            if current[claim] == "in_progress":
                client.post(
                    f"/api/claims/{claim}/failure",
                    json={"reason": "the run ended while it was in progress"},
                )


def run_queue(
    limit: int | None, thread_id: str, llm: BaseChatModel | None = None
) -> str:
    """Work the queue, at most limit claims, and return the run's summary."""
    llm = llm or core.model()
    with core.backend() as client:
        waiting = sum(1 for s in statuses().values() if s == "waiting")
        cap = min(limit, waiting) if limit else waiting
        run_id = client.post("/api/runs", json={"cap": cap}).json()["run_id"]
        instructions = client.get("/api/instructions/queue").text
    run = QueueRun(run_id, cap, llm)
    agent = create_agent(
        llm,
        tools=queue_tools(run),
        system_prompt=instructions,
        middleware=core.middleware(QUEUE_CALL_LIMIT),
    )
    reason = "The queue agent stopped before it finished the run."
    try:
        for message in messages_in(
            agent.stream(
                {
                    "messages": [
                        {
                            "role": "user",
                            "content": f"Work the queue. Your cap is {cap} claims.",
                        }
                    ]
                },
                config={"configurable": {"thread_id": thread_id}},
                stream_mode="updates",
            )
        ):
            for kind, text in steps_from(message):
                print(f"{kind}: {text}")
    except Exception as error:
        reason = f"The run stopped: {type(error).__name__}: {error}"[:300]
    finally:
        release_stuck(run)
        if not run.finished:
            close(run_id, "failed", reason)
    if not run.finished:
        raise RunFailed(reason)
    with core.backend() as client:
        return client.get("/api/runs/latest").json()["summary"]
