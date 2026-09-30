"""The queue agent, which plans a run and hands each claim to a new claim agent."""

from typing import Literal, TypedDict

from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, tool
from langgraph.checkpoint.memory import InMemorySaver

from agent import main
from agent.tools import list_claims, reply, request

REMINDERS = 2
STEPS_PER_CLAIM = 12
STOPPED = "The run stopped before this claim was finished"


class Todo(TypedDict):
    content: str
    status: Literal["to_do", "in_progress", "done", "left_for_handler"]


def queue_tools(
    run_id: str, cap: int, started: set[str], llm: BaseChatModel | None
) -> list[BaseTool]:
    """The queue agent's tools for one run, which count the claims it starts."""

    @tool
    def write_todos(todos: list[Todo]) -> str:
        """Replace the run's to-do list, sending every item with its current status."""
        return reply(request("PUT", f"/api/runs/{run_id}/todos", {"todos": todos}))

    @tool
    def work_claim(claim_id: str) -> str:
        """Hand one claim to a new claim agent, which reports back in one line."""
        if claim_id not in started and len(started) >= cap:
            return (
                f"Refused: this run can work {cap} claims, and it has started "
                f"{', '.join(sorted(started))}"
            )
        report = main.work_claim(claim_id, llm)
        if not report.startswith(f"{claim_id}  {main.NOT_STARTED}"):
            started.add(claim_id)
        print(report, flush=True)
        return report

    return [list_claims, write_todos, work_claim]


def waiting() -> list[str]:
    """Return the ids of the claims waiting in the queue."""
    claims = main.call_backend("GET", "/api/claims")
    return [claim["claim_id"] for claim in claims if claim["status"] == "waiting"]


def recover() -> None:
    """Put back in the queue any claim left in progress by a run that stopped."""
    for claim in main.call_backend("GET", "/api/claims"):
        if claim["status"] == "in_progress":
            path = f"/api/claims/{claim['claim_id']}/failure"
            main.call_backend("POST", path, {"reason": STOPPED})


def missed(cap: int, started: set[str]) -> list[str]:
    """Return the waiting claims the run should still work: its own, then new ones."""
    ids = waiting()
    own = [claim_id for claim_id in ids if claim_id in started]
    others = [claim_id for claim_id in ids if claim_id not in started]
    return own + others[: cap - len(started)]


def run_queue(
    cap: int | None,
    llm: BaseChatModel | None = None,
    claim_llm: BaseChatModel | None = None,
) -> None:
    """Work the queue with a queue agent, up to cap claims or every waiting claim."""
    recover()
    count = len(waiting())
    if count == 0:
        print("No claims are waiting")
        return
    cap = count if cap is None else min(cap, count)
    run_id = main.call_backend("POST", "/api/runs", {"cap": cap})["run_id"]
    started: set[str] = set()
    agent = create_agent(
        llm or main.model(),
        tools=queue_tools(run_id, cap, started, claim_llm),
        system_prompt=main.call_backend("GET", "/api/instructions")["queue"],
        checkpointer=InMemorySaver(),
    )
    config: RunnableConfig = {
        "configurable": {"thread_id": run_id},
        "recursion_limit": STEPS_PER_CLAIM * (cap + 2),
    }
    message = f"Please work the queue. This run can work up to {cap} claims."
    try:
        state = agent.invoke(
            {"messages": [{"role": "user", "content": message}]}, config
        )
        for _ in range(REMINDERS):
            left = missed(cap, started)
            if not left:
                break
            reminder = (
                "These claims are still waiting within the run's cap: "
                f"{', '.join(left)}. Please work them, then finish with the summary."
            )
            state = agent.invoke(
                {"messages": [{"role": "user", "content": reminder}]}, config
            )
    except Exception as error:
        summary = f"The run stopped: {main.describe(error)}"
        main.call_backend("POST", f"/api/runs/{run_id}/finish", {"summary": summary})
        raise
    summary = state["messages"][-1].text or "The run finished without a summary."
    main.call_backend("POST", f"/api/runs/{run_id}/finish", {"summary": summary})
    print(summary)
