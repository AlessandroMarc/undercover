"""The agent as an AgentCore app: one entrypoint takes the payload of each operation
the app asks for, answers at once, and hands the work to the dispatcher, the harness
or the improver on a thread of its own, which the AgentCore app's /ping reports as
busy until it ends. npm run dev serves it on port 8080, and runtime/main.py runs it
on AgentCore Runtime. Nothing happens as it's imported: it gets ready on its first
request."""

import logging
import random
import secrets
import threading
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from typing import Annotated, Any, Literal

from bedrock_agentcore.runtime import BedrockAgentCoreApp, RequestContext
from bedrock_agentcore.runtime.models import AUTHORIZATION_HEADER
from langchain_core.language_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.postgres import PostgresSaver
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError
from starlette.exceptions import HTTPException

from agent import api, identity, improver, improver_api
from agent.connection import Refused, api_key
from agent.console import describe, show_reports
from agent.dispatcher import WorkInRun, work_run
from agent.handler_answer import SENT_BACK, answer_of
from agent.harness import (
    ClaimAgent,
    NewAgent,
    Pool,
    claim_graphs,
    open_checkpoint_pool,
    paused,
    resume,
    work_in_run,
)
from agent.heartbeat import beating

ACCEPTED = {"accepted": True}
HEALTHY = {"healthy": True}
# The most claim agents at once, as the backend and the dashboard also allow.
MOST_AGENTS = 25
A_DISPATCH = "A dispatch is running"
AN_EVALUATION = "An evaluation is running"
A_ROUND = "Round {number} is running"
A_ROUND_STARTING = "A round is starting"
RESTARTED = "The agent restarted"
NOT_PAUSED = "Claim {claim_id} isn't paused for a handler"
NO_ANSWER = "Claim {claim_id} has no answer from a handler yet"
NOT_READY = "The agent couldn't get ready: {error}"
NEEDS_THE_KEY = "This needs the agent's API key"
UNKNOWN_OPERATION = "Unknown operation: {operation}"
NO_OPERATION = "The payload names no operation"
NOT_AN_OBJECT = "The payload isn't a JSON object"

log = logging.getLogger(__name__)

app = BedrockAgentCoreApp()

Agents = Annotated[int, Field(ge=1, le=MOST_AGENTS)]


class Operation(BaseModel):
    """A payload: it names its operation and carries every input, each of the right
    type, and no other."""

    model_config = ConfigDict(extra="forbid", strict=True)


class Health(Operation):
    operation: Literal["health"]


class StartDispatch(Operation):
    operation: Literal["start_dispatch"]
    agents: Agents


class StartEvaluation(Operation):
    operation: Literal["start_evaluation"]
    agents: Agents
    evaluation_set: api.EvaluationSet
    tiny: bool


class StartRound(Operation):
    operation: Literal["start_round"]
    handler_id: str


class ReviewProposal(Operation):
    operation: Literal["review_proposal"]
    round_id: str
    proposal_id: str
    review: improver_api.Review
    handler_id: str
    reason: str


class ResumeClaim(Operation):
    operation: Literal["resume_claim"]
    claim_id: str


Payload = Annotated[
    Health
    | StartDispatch
    | StartEvaluation
    | StartRound
    | ReviewProposal
    | ResumeClaim,
    Field(discriminator="operation"),
]
PAYLOADS: TypeAdapter[Payload] = TypeAdapter(Payload)

# How to build the claim agents of a version of the claim agent for a kind of run,
# or for no run, each with a saver of its own.
ClaimAgents = Callable[[dict[str, Any], api.RunKind | None], NewAgent]


@dataclass
class Workers:
    """What the agent's work needs: a version's claim agents, the improver's model
    for a round, and the saver of the improver's progress."""

    claim_agents: ClaimAgents
    improver_model: Callable[[dict[str, Any]], BaseChatModel]
    saver: BaseCheckpointSaver[Any]


class Refusal(Exception):
    """The agent won't take the work, and why."""


def workers_on(pool: Pool) -> Workers:
    """The claim agents and the improver, on the process's checkpoint pool."""
    return Workers(
        partial(claim_graphs, pool=pool),
        improver.improver_model,
        PostgresSaver(pool),
    )


def get_ready() -> Workers:
    """Get ready to work. On Runtime, reseed the random numbers, which every session
    starts with from one snapshot, and fetch the credentials. Then set up the report
    lines, check the agent's key is set, mark stopped the runs and rounds an earlier
    process left running, and open the checkpoint pool. Raise a 503 that says what
    went wrong, so the next request tries again."""
    try:
        if identity.on_runtime():
            random.seed()
            identity.fetch_credentials()
        show_reports()
        api_key()
        api.stop_runs()
        improver_api.stop_rounds(RESTARTED)
        return workers_on(open_checkpoint_pool())
    except Exception as error:  # any failure leaves the agent to get ready again
        raise HTTPException(503, NOT_READY.format(error=describe(error))) from error


class Ready:
    """The agent's workers, made once in its process, on its first request."""

    def __init__(self) -> None:
        self.guard = threading.Lock()
        self.workers: Workers | None = None

    def get(self) -> Workers:
        """Return the workers, getting ready first if no request has yet."""
        with self.guard:
            if self.workers is None:
                self.workers = get_ready()
            return self.workers


ready = Ready()


def read(payload: Any) -> Payload:
    """Read a payload, or refuse it with a 400 that says what's wrong."""
    try:
        return PAYLOADS.validate_python(payload)
    except ValidationError as error:
        raise HTTPException(400, what_is_wrong(error)) from error


def what_is_wrong(error: ValidationError) -> str:
    """Say what's wrong with a payload: an operation the agent doesn't know, or
    each input that's missing, wrong or extra."""
    problems = []
    for problem in error.errors():
        if problem["type"] == "union_tag_invalid":
            operation = problem.get("ctx", {}).get("tag")
            problems.append(UNKNOWN_OPERATION.format(operation=operation))
        elif problem["type"] == "union_tag_not_found":
            problems.append(NO_OPERATION)
        elif not problem["loc"]:
            problems.append(NOT_AN_OBJECT)
        else:
            field = ".".join(str(part) for part in problem["loc"][1:])
            problems.append(f"{field}: {problem['msg']}")
    return "; ".join(problems)


def check_key(context: RequestContext) -> None:
    """Off Runtime, refuse a request without the agent's key as its bearer token
    with a 401. On Runtime, AWS has already checked that the caller may invoke the
    agent."""
    if identity.on_runtime():
        return
    given = (context.request_headers or {}).get(AUTHORIZATION_HEADER, "")
    if not secrets.compare_digest(given.encode(), f"Bearer {api_key()}".encode()):
        raise HTTPException(401, NEEDS_THE_KEY)


class OneAtATime:
    """The one dispatch, evaluation or stretch of a round the agent works at a time,
    and what it is, which a refusal names."""

    def __init__(self) -> None:
        self.guard = threading.Lock()
        self.what: str | None = None

    def take(self, what: str) -> None:
        """Take the one thing at a time for some work, or refuse, naming what is
        running."""
        with self.guard:
            if self.what is not None:
                raise Refusal(self.what)
            self.what = what

    def rename(self, what: str) -> None:
        """Say better what is running, once it is known."""
        with self.guard:
            self.what = what

    def release(self) -> None:
        with self.guard:
            self.what = None


one_at_a_time = OneAtATime()


def in_background(name: str, work: Callable[[], object]) -> None:
    """Register the work with the AgentCore app, so its /ping says HealthyBusy
    until the work ends, however it ends, and run it on a thread of its own."""
    task_id = app.add_async_task(name)

    def run() -> None:
        try:
            work()
        finally:
            app.complete_async_task(task_id)

    threading.Thread(target=run, name=name, daemon=True).start()


def claim_work(run: dict[str, Any], claim_agents: ClaimAgents) -> WorkInRun:
    """How to work one of a run's claims, on the claim agents of the run's own
    version, tagged with its round when it has one."""
    new_agent = claim_agents(api.get_version(run["version"]), run["kind"])
    tags = (run["round_id"],) if run["round_id"] else ()
    return partial(work_in_run, new_agent=new_agent, tags=tags)


def evaluate(run: dict[str, Any], claim_agents: ClaimAgents) -> None:
    """Work one of a round's evaluations through the dispatcher."""
    work_run(run, claim_work(run, claim_agents))


def work_in_background(
    create: Callable[[], dict[str, Any]], claim_agents: ClaimAgents
) -> None:
    """Create a run and work it, then let the next work start. A run whose
    dispatcher fails is marked stopped."""
    try:
        run = create()
        work_run(run, claim_work(run, claim_agents))
    except ConnectionError as error:  # a route's server isn't answering
        log.error("The run stopped: %s", error)
        api.stop_runs()
    except Exception:
        log.exception("The run stopped")
        api.stop_runs()
    finally:
        one_at_a_time.release()


def first_evaluations(round: dict[str, Any], workers: Workers) -> bool:
    """Work the evaluations the round's starting version still needs, one at a time,
    and say whether the round is still open after them: the spending limit or a
    handler may have stopped it."""
    for _ in round["first_evaluations"]:
        run = improver_api.create_round_evaluation(round["round_id"])
        evaluate(run, workers.claim_agents)
        if not still_open(round):
            return False
    return True


def still_open(round: dict[str, Any]) -> bool:
    """Say whether the round is still open: a handler or the spending limit may
    have stopped it."""
    return improver_api.get_round(round["round_id"])["status"] == improver_api.OPEN


def stretch(round: dict[str, Any], start: improver.Start, workers: Workers) -> None:
    """Run the improver until it waits for a handler, then record its proposal, or
    until it ends, then finish the round if it is still open. A proposal the
    backend refuses, such as a second change, goes back to the improver as a
    rejection with the backend's reason."""
    while proposal := improver.work_stretch(
        round,
        start,
        partial(evaluate, claim_agents=workers.claim_agents),
        workers.saver,
        workers.improver_model(round),
    ):
        try:
            improver.record_proposal(round["round_id"], proposal)
            return
        except Refused as refusal:
            start = improver.resume(improver_api.REJECTED, refusal.answer)
    if still_open(round):
        improver_api.finish_round(round["round_id"])


def stop_the_round(error: Exception) -> None:
    """Stop a round whose work failed, giving the error as the reason, and an
    evaluation it left running."""
    log.exception("The round stopped")
    api.stop_runs()
    improver_api.stop_rounds(describe(error))


def work_round(handler_id: str, workers: Workers) -> None:
    """Create a round, work its first evaluations, then the improver's first
    stretch, and let the next work start."""
    try:
        round = improver_api.create_round(handler_id)
    except Exception:  # no round to stop, so the next work may start
        log.exception("The round didn't start")
        one_at_a_time.release()
        return
    one_at_a_time.rename(A_ROUND.format(number=round["number"]))
    try:
        if first_evaluations(round, workers):
            stretch(round, improver.begin(), workers)
    except Exception as error:
        stop_the_round(error)
    finally:
        one_at_a_time.release()


def carry_the_round_on(
    round: dict[str, Any], start: improver.Start, workers: Workers
) -> None:
    """Carry the improver on after a handler's review, and let the next work start."""
    try:
        stretch(round, start, workers)
    except Exception as error:
        stop_the_round(error)
    finally:
        one_at_a_time.release()


def resume_telling_the_app(claim_id: str, agent: ClaimAgent) -> None:
    """Resume a paused claim, telling the app every minute that the resume is still
    working on it."""
    with beating(partial(api.record_claim_heartbeat, claim_id)):
        resume(claim_id, agent)


def start_dispatch(request: StartDispatch, workers: Workers) -> None:
    """Start a dispatch with up to N claim agents at once."""
    one_at_a_time.take(A_DISPATCH)
    create = partial(api.create_dispatch, request.agents)
    in_background("dispatch", partial(work_in_background, create, workers.claim_agents))


def start_evaluation(request: StartEvaluation, workers: Workers) -> None:
    """Start an evaluation with up to N claim agents at once."""
    one_at_a_time.take(AN_EVALUATION)
    create = partial(
        api.create_evaluation, request.evaluation_set, request.tiny, request.agents
    )
    in_background(
        "evaluation", partial(work_in_background, create, workers.claim_agents)
    )


def start_round(request: StartRound, workers: Workers) -> None:
    """Start a round of the improver for the handler who asked."""
    one_at_a_time.take(A_ROUND_STARTING)
    in_background("round", partial(work_round, request.handler_id, workers))


def review_proposal(request: ReviewProposal, workers: Workers) -> None:
    """Record a handler's review of a proposal, then carry the improver on."""
    one_at_a_time.take(A_ROUND_STARTING)
    try:
        round = improver_api.get_round(request.round_id)
        one_at_a_time.rename(A_ROUND.format(number=round["number"]))
        improver_api.record_review(
            request.round_id,
            request.proposal_id,
            request.review,
            request.handler_id,
            request.reason,
        )
    except Exception:  # nothing to carry on, so the next work may start
        one_at_a_time.release()
        raise
    start = improver.resume(request.review, request.reason)
    in_background("round", partial(carry_the_round_on, round, start, workers))


def resume_claim(request: ResumeClaim, workers: Workers) -> None:
    """Resume a paused claim with its handler's answer, beside any other work,
    taking a sent-back claim first."""
    claim_id = request.claim_id
    claim = api.get_claim(claim_id)
    agent = workers.claim_agents(api.get_current_version(), None)()
    if not paused(claim, agent):
        raise Refusal(NOT_PAUSED.format(claim_id=claim_id))
    answer = answer_of(claim)
    if answer is None:
        raise Refusal(NO_ANSWER.format(claim_id=claim_id))
    if answer["answer"] == SENT_BACK:
        api.take_claim(claim_id, None)
    in_background("resume", partial(resume_telling_the_app, claim_id, agent))


def start(request: Payload, workers: Workers) -> dict[str, Any]:
    """Hand an operation its work, and answer that the agent took it."""
    match request:
        case Health():
            return HEALTHY
        case StartDispatch():
            start_dispatch(request, workers)
        case StartEvaluation():
            start_evaluation(request, workers)
        case StartRound():
            start_round(request, workers)
        case ReviewProposal():
            review_proposal(request, workers)
        case ResumeClaim():
            resume_claim(request, workers)
    return ACCEPTED


@app.entrypoint
def invoke(payload: Any, context: RequestContext) -> dict[str, Any]:
    """Take one operation's payload: get ready, read it, check the key unless it's
    the health check, and start its work, or say why the agent won't."""
    workers = ready.get()
    request = read(payload)
    if not isinstance(request, Health):
        check_key(context)
    try:
        return start(request, workers)
    except Refusal as refusal:
        return {"refused": str(refusal)}
    except Refused as refused:  # the app's refusal, such as a claim it doesn't know
        return {"refused": refused.detail}
