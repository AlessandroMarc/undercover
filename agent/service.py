"""The agent's service: it works the dispatches and evaluations the backend starts,
one at a time, and picks a claim back up after a handler's sign-off. npm run dev
starts it beside the backend and the dashboard."""

import logging
import threading
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from functools import partial
from typing import Annotated, Any

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from agent import api
from agent.console import show_reports
from agent.dispatcher import work_run
from agent.harness import NewGraph, carry_on, checkpoint_pool, claim_graphs, model

ALREADY_RUNNING = "A dispatch or an evaluation is already running"
# The most claim agents at once, as the backend and the dashboard also allow.
MOST_AGENTS = 25
NO_REASONING_EFFORT = "none"

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Keep the checkpoint pool open while the service runs, after marking any run
    an earlier service left running as stopped."""
    show_reports()
    with checkpoint_pool() as pool:
        app.state.pool = pool
        api.stop_runs()
        yield


app = FastAPI(title="UnderCover Agent", lifespan=lifespan)

# One dispatch or evaluation at a time, and the claims being resumed after a
# sign-off, which a dispatch leaves alone.
one_run = threading.Lock()
resuming: set[str] = set()


@app.exception_handler(api.Refused)
def refused(_: Request, error: api.Refused) -> JSONResponse:
    """Pass on the backend's refusal, such as a claim it doesn't know."""
    return JSONResponse({"detail": error.detail}, status_code=error.status_code)


@dataclass
class ClaimAgents:
    """The service's claim agents: their model, its reasoning effort, and how to
    build a claim graph with a saver of its own."""

    model: str
    reasoning_effort: str
    new_graph: NewGraph


def claim_agents(request: Request) -> ClaimAgents:
    """Build the model for one request, and claim graphs on the service's pool."""
    llm = model()
    return ClaimAgents(
        llm.model_name,
        llm.reasoning_effort or NO_REASONING_EFFORT,
        claim_graphs(llm, request.app.state.pool),
    )


Agents = Annotated[ClaimAgents, Depends(claim_agents)]


class DispatchRequest(BaseModel):
    agents: int = Field(ge=1, le=MOST_AGENTS, description="Claim agents at once")


class EvaluationRequest(DispatchRequest):
    evaluation_set: api.EvaluationSet
    tiny: bool = Field(description="Only the set's five tiny claims")


def take_the_run() -> None:
    """Take the one run the service works at a time, or refuse with a 409."""
    if not one_run.acquire(blocking=False):
        raise HTTPException(409, ALREADY_RUNNING)


def work_in_background(
    create: Callable[[], dict[str, Any]], agents: ClaimAgents
) -> None:
    """Create a run through the backend and work it, then let the next run start. A
    run whose dispatcher fails is marked stopped."""
    try:
        work_run(create(), agents.new_graph, resuming)
    except Exception:
        log.exception("The run stopped")
        api.stop_runs()
    finally:
        one_run.release()


@app.get("/api/health", operation_id="health")
def health() -> dict[str, str]:
    """Check that the agent's service is running."""
    return {"status": "ok"}


@app.post("/api/dispatches", operation_id="start_dispatch", status_code=202)
def start_dispatch(
    request: DispatchRequest, agents: Agents, background: BackgroundTasks
) -> dict[str, str]:
    """Start a dispatch with up to N claim agents at once."""
    take_the_run()
    create = partial(
        api.create_dispatch, request.agents, agents.model, agents.reasoning_effort
    )
    background.add_task(work_in_background, create, agents)
    return {"status": "accepted"}


def resume(claim_id: str, agents: ClaimAgents) -> None:
    """Carry a signed-off claim on, keeping dispatches away from it meanwhile."""
    try:
        carry_on(claim_id, None, agents.new_graph())
    finally:
        resuming.discard(claim_id)


@app.post("/api/claims/{claim_id}/resume", operation_id="resume_claim", status_code=202)
def resume_claim(
    claim_id: str, agents: Agents, background: BackgroundTasks
) -> dict[str, str]:
    """Pick a claim back up after a handler's sign-off, without waiting for it."""
    claim = api.get_claim(claim_id)
    signed_off = claim["decision"] and claim["decision"]["signed_off_by"]
    if claim["status"] != api.Status.IN_PROGRESS or not signed_off:
        raise HTTPException(409, f"Claim {claim_id} has no sign-off waiting to be paid")
    resuming.add(claim_id)
    background.add_task(resume, claim_id, agents)
    return {"status": "accepted"}


@app.post("/api/evaluations", operation_id="start_evaluation", status_code=202)
def start_evaluation(
    request: EvaluationRequest, agents: Agents, background: BackgroundTasks
) -> dict[str, str]:
    """Start an evaluation with up to N claim agents at once."""
    take_the_run()
    create = partial(
        api.create_evaluation,
        request.evaluation_set,
        request.tiny,
        request.agents,
        agents.model,
        agents.reasoning_effort,
    )
    background.add_task(work_in_background, create, agents)
    return {"status": "accepted"}
