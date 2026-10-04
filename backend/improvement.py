"""The backend's operations on the improver's rounds. Only the agent's service writes
them, under /api/rounds; the dashboard reads and acts on them under
/api/improvement. The backend keeps a proposal from taking effect until a handler
approves it, keeps or rolls back each version by the business's rule, and refuses
anything a round records once it has finished or been stopped."""

import uuid
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import Connection, RowMapping, func, insert, select, update

from backend import agent_service, spending, verdict
from backend.database import (
    LUNA,
    handler_decisions,
    handlers,
    improver_calls,
    now,
    proposals,
    recipes,
    rounds,
    runs,
    versions,
)
from backend.dependencies import Database, refuse_unless_senior, senior
from backend.diffs import diff
from backend.free_models import model_or_free
from backend.lookups import (
    allowed_models,
    current_settings,
    current_version_number,
    settings_number,
    version_row,
)
from backend.models import (
    Accepted,
    AgentAnswer,
    ChangeProposalRequest,
    ClaimAgentVersion,
    ClaimBesideHandler,
    CreateRoundRequest,
    Diff,
    EarlierRound,
    Evaluation,
    EvaluationSet,
    EvaluationSetResults,
    Handler,
    HandlerAnswer,
    Improvement,
    ImproverCallRequest,
    ImproverView,
    JudgeAnswer,
    Measures,
    NewNumber,
    Proposal,
    ProposalKind,
    RecipeDetails,
    RecipeProposalRequest,
    RecipeSummary,
    RejectionRequest,
    Review,
    ReviewRequest,
    RoundForService,
    RoundReviewView,
    RoundStatus,
    RoundSummary,
    RoundView,
    RunStatus,
    ScoredClaim,
    Spending,
    StopRoundsRequest,
    Verdict,
    VerdictResult,
    VerdictScores,
    VersionPoint,
    WaitingProposal,
)
from backend.round_state import (
    EVALUATIONS,
    evaluations_of,
    finished_of,
    open_round,
    roll_back,
    round_row,
    spending_limit,
    spending_of,
    stage_of,
    stop,
    tried_version,
    waiting_proposal,
)
from backend.scoreboard import (
    Expected,
    expected_answers,
    round_evaluations,
    score,
    version_scores,
)

INSTRUCTIONS = Path(__file__).parent / "instructions"
# The improver's model, unless students on free models have one of their own.
IMPROVER_MODEL = (LUNA, "medium")
ROUND_OPEN = "Round {number} is open. Finish or stop it first."
NOT_WAITING = "Proposal {proposal_id} isn't waiting for a handler: it was {review}"
# How many of the right claims the improver reads, those the judge graded lowest.
EXPLAINED_LEAST_WELL = 5
YES_FROM = 0.5

router = APIRouter()

StartsRounds = Annotated[Handler, Depends(senior("start a round"))]
StopsRounds = Annotated[Handler, Depends(senior("stop a round"))]
REVIEWING = "approve or reject the improver's proposals"
ReviewsProposals = Annotated[Handler, Depends(senior(REVIEWING))]


# Finding things.


def handler_row(db: Connection, handler_id: str) -> Handler:
    """Return a handler by id, or raise a 404."""
    query = select(handlers).where(handlers.c.handler_id == handler_id)
    row = db.execute(query).mappings().first()
    if row is None:
        raise HTTPException(404, f"Handler {handler_id} not found")
    return Handler(**row)


def proposal_in(db: Connection, row: RowMapping, proposal_id: str) -> RowMapping:
    """Return one of a round's proposals, or raise a 404."""
    query = select(proposals).where(
        proposals.c.proposal_id == proposal_id,
        proposals.c.round_id == row["round_id"],
    )
    proposal = db.execute(query).mappings().first()
    if proposal is None:
        raise HTTPException(
            404, f"Proposal {proposal_id} not found in round {row['number']}"
        )
    return proposal


def the_one_waiting(db: Connection, row: RowMapping, proposal_id: str) -> RowMapping:
    """Return a round's proposal if it is the one waiting for a handler, or raise a
    404 or a 409, so a review never lands on a proposal the handler didn't see."""
    proposal = proposal_in(db, row, proposal_id)
    if proposal["review"] is not None:
        raise HTTPException(
            409,
            NOT_WAITING.format(proposal_id=proposal_id, review=proposal["review"]),
        )
    return proposal


def current_recipe(db: Connection) -> RowMapping:
    """Return the recipe the next round follows: the newest approved."""
    query = select(recipes).order_by(recipes.c.number.desc()).limit(1)
    return db.execute(query).mappings().one()


def round_recipe(db: Connection, round_id: str) -> RowMapping | None:
    """Return the recipe a round made from an approved proposal, if any."""
    query = select(recipes).where(recipes.c.round_id == round_id)
    return db.execute(query).mappings().first()


def is_allowed(db: Connection, model: str, reasoning_effort: str) -> bool:
    """Say whether the claim agent may use a model at a reasoning effort."""
    return any(
        allowed.model == model and reasoning_effort in allowed.reasoning_efforts
        for allowed in allowed_models(db)
    )


def refuse_while_a_round_is_open(db: Connection) -> None:
    """Raise a 409 naming the round that's open, if there is one."""
    query = select(rounds.c.number).where(rounds.c.status == RoundStatus.OPEN)
    number = db.execute(query).scalar_one_or_none()
    if number is not None:
        raise HTTPException(409, ROUND_OPEN.format(number=number))


def refuse_while_waiting(db: Connection, row: RowMapping) -> None:
    """Raise a 409 while one of the round's proposals waits for a handler."""
    if waiting_proposal(db, row["round_id"]):
        raise HTTPException(
            409, f"Round {row['number']} has a proposal waiting for a handler"
        )


def first_evaluations(db: Connection, version: int) -> list[EvaluationSet]:
    """Return the sets of the evaluations a version still needs before a round can
    improve on it: one on the evaluation set and two on the held-out set, less the
    whole-set evaluations rounds have finished on it."""
    have = {s: len(runs_) for s, runs_ in round_evaluations(db, version).items()}
    needed = []
    for evaluation_set in EVALUATIONS:
        if have[evaluation_set]:
            have[evaluation_set] -= 1
        else:
            needed.append(evaluation_set)
    return needed


# Shapes.


def to_proposal(row: RowMapping) -> Proposal:
    """A proposal as the service and the improver read it."""
    proposed: dict[str, Any] = row["proposal"]
    return Proposal(
        **{field: row[field] for field in Proposal.model_fields if field in row},
        reason=proposed["reason"],
        instructions=proposed.get("instructions"),
        model=proposed.get("model"),
        reasoning_effort=proposed.get("reasoning_effort"),
        recipe=proposed.get("recipe"),
    )


def for_the_service(db: Connection, row: RowMapping) -> RoundForService:
    """A round as the agent's service works it, with the improver's instructions
    around the round's recipe."""
    recipe = db.execute(
        select(recipes.c.recipe).where(recipes.c.number == row["recipe"])
    ).scalar_one()
    improver = (INSTRUCTIONS / "improver.md").read_text(encoding="utf-8")
    return RoundForService(
        **row,
        instructions=f"{improver}\n{recipe}",
        models_allowed=allowed_models(db),
    )


def measures_or_none(stored: dict[str, Any] | None) -> Measures | None:
    return Measures(**stored) if stored else None


# What the improver reads.


def yes_or_no(chance: float) -> Literal["yes", "no"]:
    """A check as the improver reads it: yes from even odds."""
    return "yes" if chance >= YES_FROM else "no"


def beside_handler(claim: ScoredClaim, handler: RowMapping) -> ClaimBesideHandler:
    """An evaluation's copy as the improver reads it: under its original's id, the
    agent's answer beside the handler's, and the judge's grade."""
    grade = claim.grade
    return ClaimBesideHandler(
        claim_id=claim.copy_of,
        summary=claim.summary,
        agent=AgentAnswer(
            decision=claim.decision,
            payout=claim.payout,
            reason=claim.reason,
            section=claim.section,
        ),
        handler=HandlerAnswer(
            decision=handler["decision"],
            payout=handler["payout"],
            reason=handler["reason"],
            reference=handler["reference"],
        ),
        judge=grade
        and JudgeAnswer(
            grade=grade.score,
            letter=grade.letter,
            same_grounds=yes_or_no(grade.same_grounds),
            same_section=yes_or_no(grade.same_section),
        ),
    )


def evaluation_set_results(
    db: Connection, version: int, expected: Expected
) -> EvaluationSetResults:
    """From a version's latest round evaluation on the evaluation set, the claims it
    got wrong and the right ones the judge graded lowest, with the handlers'
    reasons. Nothing from the held-out set."""
    latest = round_evaluations(db, version)[EvaluationSet.EVALUATION][-1:]
    if not latest:
        return EvaluationSetResults(wrong=[], explained_least_well=[])
    claims = score(db, latest[0], expected).claims
    handlers_ = handler_reasons(db)
    right = [c for c in claims if c.right]
    weakest = sorted(right, key=lambda c: c.grade.score if c.grade else 3)
    return EvaluationSetResults(
        wrong=[beside_handler(c, handlers_[c.copy_of]) for c in claims if not c.right],
        explained_least_well=[
            beside_handler(c, handlers_[c.copy_of])
            for c in weakest[:EXPLAINED_LEAST_WELL]
        ],
    )


def handler_reasons(db: Connection) -> dict[str, RowMapping]:
    """The handlers' decisions on the evaluation set, with their reasons."""
    query = select(handler_decisions).where(
        handler_decisions.c.evaluation_set == EvaluationSet.EVALUATION
    )
    return {row["claim_id"]: row for row in db.execute(query).mappings()}


def earlier_round(db: Connection, row: RowMapping) -> EarlierRound:
    """What an earlier round tried and how it came out."""
    version = tried_version(db, row["round_id"])
    tried = dict(version) if version else {}
    return EarlierRound(
        round=row["number"],
        recipe_version=row["recipe"],
        version=tried.get("number"),
        model=tried.get("model"),
        reasoning_effort=tried.get("reasoning_effort"),
        reason=tried.get("reason"),
        held_out_before=measures_or_none(row["held_out_before"]),
        held_out_after=measures_or_none(row["held_out_after"]),
        verdict=tried.get("verdict"),
        why=tried.get("verdict_reason"),
    )


def improver_view(db: Connection, row: RowMapping) -> ImproverView:
    """What the improver reads in a round, as the lab's read_results gives it."""
    current = version_row(db, current_version_number(db))
    expected = expected_answers(db)
    settings = settings_number(db, row["settings"])
    earlier = select(rounds).where(rounds.c.number < row["number"])
    return ImproverView(
        current_version=ClaimAgentVersion(**current),
        scores=version_scores(db, current["number"], expected),
        evaluation_set=evaluation_set_results(db, current["number"], expected),
        earlier_rounds=[
            earlier_round(db, earlier_row)
            for earlier_row in db.execute(earlier.order_by(rounds.c.number)).mappings()
        ],
        objectives_on_the_held_out_set=settings.objectives,
        noise=settings.noise,
        tolerance=settings.tolerance,
        rule=verdict.RULE,
        spending=spending_of(db, row),
        models_allowed=allowed_models(db),
    )


# What the Improvement page shows.


def reviews_of(db: Connection, round_id: str) -> list[RoundReviewView]:
    """Who approved or rejected each of a round's proposals, and when."""
    query = (
        select(proposals)
        .where(proposals.c.round_id == round_id, proposals.c.review.is_not(None))
        .order_by(proposals.c.reviewed_at)
    )
    return [RoundReviewView(**row) for row in db.execute(query).mappings()]


def summary_of(db: Connection, row: RowMapping) -> RoundSummary:
    """A round: where it has got to, what it tried, how that came out, who
    approved or rejected what, and what it cost."""
    version = tried_version(db, row["round_id"])
    stage, progress = (
        stage_of(db, row) if row["status"] == RoundStatus.OPEN else (None, None)
    )
    measures = {"held_out_before", "held_out_after"}
    return RoundSummary(
        **{key: value for key, value in row.items() if key not in measures},
        stage=stage,
        progress=progress,
        spending_limit=spending_limit(db, row),
        cost=spending.spent(db, row["round_id"]),
        version=version["number"] if version else None,
        model=version["model"] if version else None,
        reasoning_effort=version["reasoning_effort"] if version else None,
        reason=version["reason"] if version else None,
        verdict=version["verdict"] if version else None,
        verdict_reason=version["verdict_reason"] if version else None,
        held_out_before=measures_or_none(row["held_out_before"]),
        held_out_after=measures_or_none(row["held_out_after"]),
        reviews=reviews_of(db, row["round_id"]),
    )


def waiting_view(db: Connection, row: RowMapping) -> WaitingProposal | None:
    """The proposal waiting for a handler while the round is open, with what it
    changes from the current version or recipe."""
    waiting = waiting_proposal(db, row["round_id"])
    if waiting is None or row["status"] != RoundStatus.OPEN:
        return None
    proposal = to_proposal(waiting)
    if proposal.kind == ProposalKind.RECIPE:
        return WaitingProposal(
            **proposal.model_dump(),
            diff=diff(current_recipe(db)["recipe"], proposal.recipe or ""),
            model_before=None,
            reasoning_effort_before=None,
            model_after=None,
            reasoning_effort_after=None,
        )
    current = version_row(db, current_version_number(db))
    return WaitingProposal(
        **proposal.model_dump(),
        diff=diff(current["instructions"], proposal.instructions or ""),
        model_before=current["model"],
        reasoning_effort_before=current["reasoning_effort"],
        model_after=proposal.model,
        reasoning_effort_after=proposal.reasoning_effort,
    )


def view_of(db: Connection, row: RowMapping, expected: Expected) -> RoundView:
    """A round in full: its summary, the proposal waiting and its evaluations."""
    query = select(runs).where(runs.c.round_id == row["round_id"])
    evaluations = [
        Evaluation(**score(db, run, expected).model_dump(exclude={"claims"}))
        for run in db.execute(query.order_by(runs.c.number)).mappings()
    ]
    return RoundView(
        **summary_of(db, row).model_dump(),
        waiting=waiting_view(db, row),
        evaluations=evaluations,
    )


def version_point(db: Connection, row: RowMapping, expected: Expected) -> VersionPoint:
    """A version's held-out accuracy and grade, for the chart."""
    held_out = version_scores(db, row["number"], expected).held_out
    return VersionPoint(
        number=row["number"],
        verdict=row["verdict"] if row["round_id"] else None,
        accuracy=held_out.accuracy if held_out else None,
        grade=held_out.grade if held_out else None,
    )


def recipe_diff(db: Connection, row: RowMapping) -> Diff | None:
    """What a recipe changed from the one before, or none for the first."""
    before = db.execute(
        select(recipes.c.recipe).where(recipes.c.number == row["number"] - 1)
    ).scalar_one_or_none()
    return diff(before, row["recipe"]) if before is not None else None


def recipe_summary(
    row: RowMapping, current: int, changes: Diff | None
) -> RecipeSummary:
    """A recipe with how many lines it changed from the one before."""
    return RecipeSummary(
        **row,
        current=row["number"] == current,
        lines_added=changes.added if changes else 0,
        lines_removed=changes.removed if changes else 0,
    )


def improvement_page(db: Connection) -> Improvement:
    """Everything the Improvement page shows."""
    expected = expected_answers(db)
    all_rounds = list(
        db.execute(select(rounds).order_by(rounds.c.number.desc())).mappings()
    )
    tried = select(versions).where(versions.c.round_id.is_not(None))
    current = current_recipe(db)["number"]
    all_recipes = db.execute(select(recipes).order_by(recipes.c.number.desc()))
    return Improvement(
        round=view_of(db, all_rounds[0], expected) if all_rounds else None,
        rounds=[summary_of(db, row) for row in all_rounds],
        first_version=version_point(db, version_row(db, 1), expected),
        versions_tried=[
            version_point(db, row, expected)
            for row in db.execute(tried.order_by(versions.c.number)).mappings()
        ],
        recipes=[
            recipe_summary(row, current, recipe_diff(db, row))
            for row in all_recipes.mappings()
        ],
    )


# The agent's service's operations on a round.


@router.post("/api/rounds", operation_id="create_round")
def create_round(request: CreateRoundRequest, db: Database) -> RoundForService:
    """Record a new round to the settings, recipe and version in force."""
    refuse_while_a_round_is_open(db)
    handler = handler_row(db, request.handler_id)
    version = current_version_number(db)
    model, reasoning_effort = model_or_free(*IMPROVER_MODEL)
    round_id = str(uuid.uuid4())
    db.execute(
        insert(rounds).values(
            round_id=round_id,
            thread_id=str(uuid.uuid4()),
            status=RoundStatus.OPEN,
            settings=current_settings(db).number,
            recipe=current_recipe(db)["number"],
            starting_version=version,
            first_evaluations=first_evaluations(db, version),
            improver_model=model,
            improver_reasoning_effort=reasoning_effort,
            started_by=handler.name,
            started_at=now(),
        )
    )
    return for_the_service(db, round_row(db, round_id))


@router.post("/api/rounds/stop", operation_id="stop_rounds")
def stop_rounds(request: StopRoundsRequest, db: Database) -> list[str]:
    """Stop every open round that isn't waiting for a handler, with the reason."""
    query = select(rounds).where(rounds.c.status == RoundStatus.OPEN)
    stopped = []
    for row in db.execute(query).mappings().all():
        if waiting_proposal(db, row["round_id"]) is None:
            stop(db, row, None, request.reason)
            stopped.append(row["round_id"])
    return stopped


@router.get("/api/rounds/{round_id}", operation_id="get_round")
def get_round(round_id: str, db: Database) -> RoundForService:
    """Get a round as the agent's service works it, with the improver's model."""
    return for_the_service(db, round_row(db, round_id))


@router.get("/api/rounds/{round_id}/results", operation_id="get_improver_view")
def get_improver_view(round_id: str, db: Database) -> ImproverView:
    """Get what the improver reads in a round: no held-out claim, only scores."""
    return improver_view(db, round_row(db, round_id))


def propose(
    db: Connection, row: RowMapping, kind: ProposalKind, proposed: dict[str, Any]
) -> Proposal:
    """Record a proposal from the improver, waiting for a handler."""
    refuse_while_waiting(db, row)
    proposal_id = str(uuid.uuid4())
    db.execute(
        insert(proposals).values(
            proposal_id=proposal_id,
            round_id=row["round_id"],
            kind=kind,
            proposal=proposed,
            proposed_at=now(),
        )
    )
    return to_proposal(proposal_in(db, row, proposal_id))


@router.post(
    "/api/rounds/{round_id}/proposals/change", operation_id="record_change_proposal"
)
def record_change_proposal(
    round_id: str, request: ChangeProposalRequest, db: Database
) -> Proposal:
    """Record the improver's proposed change, which changes nothing until approved."""
    row = open_round(db, round_id)
    tried = tried_version(db, round_id)
    if tried:
        raise HTTPException(
            409, f"Round {row['number']} has already tried version {tried['number']}"
        )
    return propose(db, row, ProposalKind.CHANGE, request.model_dump())


@router.post(
    "/api/rounds/{round_id}/proposals/recipe", operation_id="record_recipe_proposal"
)
def record_recipe_proposal(
    round_id: str, request: RecipeProposalRequest, db: Database
) -> Proposal:
    """Record the improver's proposed recipe, which changes nothing until approved."""
    row = open_round(db, round_id)
    if round_recipe(db, round_id):
        raise HTTPException(409, f"Round {row['number']} has already made a recipe")
    return propose(db, row, ProposalKind.RECIPE, request.model_dump())


@router.post(
    "/api/rounds/{round_id}/proposals/{proposal_id}/review",
    operation_id="record_review",
)
def record_review(
    round_id: str, proposal_id: str, request: ReviewRequest, db: Database
) -> Proposal:
    """Record a handler's review of the proposal waiting for one."""
    row = open_round(db, round_id)
    the_one_waiting(db, row, proposal_id)
    handler = handler_row(db, request.handler_id)
    refuse_unless_senior(db, handler, REVIEWING)
    db.execute(
        update(proposals)
        .where(proposals.c.proposal_id == proposal_id)
        .values(
            review=request.review,
            reviewed_by=handler.name,
            reviewed_at=now(),
            rejection_reason=request.reason
            if request.review == Review.REJECTED
            else None,
        )
    )
    return to_proposal(proposal_in(db, row, proposal_id))


def approved(db: Connection, row: RowMapping, kind: ProposalKind) -> RowMapping:
    """Return the round's approved proposal of a kind, or raise a 409."""
    query = select(proposals).where(
        proposals.c.round_id == row["round_id"],
        proposals.c.kind == kind,
        proposals.c.review == Review.APPROVED,
    )
    proposal = db.execute(query).mappings().first()
    if proposal is None:
        raise HTTPException(
            409, f"No {kind} has been approved in round {row['number']}"
        )
    return proposal


@router.post("/api/rounds/{round_id}/version", operation_id="create_version")
def create_version(round_id: str, db: Database) -> NewNumber:
    """Make the approved change a version under test; a repeat returns it."""
    row = open_round(db, round_id)
    tried = tried_version(db, round_id)
    if tried:
        return NewNumber(number=tried["number"])
    proposal = approved(db, row, ProposalKind.CHANGE)
    change = ChangeProposalRequest(**proposal["proposal"])
    if not is_allowed(db, change.model, change.reasoning_effort):
        raise HTTPException(
            422,
            f"{change.model} at {change.reasoning_effort} isn't allowed. "
            "Choose from the models allowed.",
        )
    number = db.execute(select(func.max(versions.c.number))).scalar_one() + 1
    db.execute(
        insert(versions).values(
            number=number,
            **change.model_dump(),
            proposed_by=f"Round {row['number']}",
            based_on=current_version_number(db),
            round_id=round_id,
            approved_by=proposal["reviewed_by"],
            approved_at=proposal["reviewed_at"],
            created_at=now(),
        )
    )
    return NewNumber(number=number)


@router.post("/api/rounds/{round_id}/recipe", operation_id="create_recipe")
def create_recipe(round_id: str, db: Database) -> NewNumber:
    """Make the approved recipe the one the next round follows; a repeat returns it."""
    row = open_round(db, round_id)
    made = round_recipe(db, round_id)
    if made:
        return NewNumber(number=made["number"])
    proposal = approved(db, row, ProposalKind.RECIPE)
    recipe = RecipeProposalRequest(**proposal["proposal"])
    number = current_recipe(db)["number"] + 1
    db.execute(
        insert(recipes).values(
            number=number,
            **recipe.model_dump(),
            proposed_by=f"Round {row['number']}",
            round_id=round_id,
            approved_by=proposal["reviewed_by"],
            approved_at=proposal["reviewed_at"],
            created_at=now(),
        )
    )
    return NewNumber(number=number)


def decide(
    db: Connection,
    row: RowMapping,
    version: RowMapping,
    new: Measures | None,
    old: Measures | None,
) -> verdict.Decided:
    """Keep or roll back a round's version by the rule, from its held-out scores
    against the current version's, to the round's settings."""
    evaluations = evaluations_of(db, row["round_id"], version["number"])
    if any(run["status"] == RunStatus.STOPPED for run in evaluations):
        return verdict.Decided(Verdict.ROLLED_BACK, "its evaluations were stopped")
    if finished_of(evaluations) < len(EVALUATIONS):
        return verdict.Decided(
            Verdict.ROLLED_BACK, "the round couldn't afford to evaluate it"
        )
    settings = settings_number(db, row["settings"])
    return verdict.keep_or_roll_back(new, old, settings)


@router.post("/api/rounds/{round_id}/verdict", operation_id="record_verdict")
def record_verdict(round_id: str, db: Database) -> VerdictResult:
    """Keep or roll back the round's version under test by the business's rule."""
    row = open_round(db, round_id)
    version = tried_version(db, round_id)
    if version is None or version["verdict"] is not None:
        raise HTTPException(409, f"Round {row['number']} has no version under test")
    expected = expected_answers(db)
    before = version_scores(db, current_version_number(db), expected).held_out
    tried = version_scores(db, version["number"], expected)
    decided = decide(db, row, version, tried.held_out, before)
    db.execute(
        update(versions)
        .where(versions.c.number == version["number"])
        .values(verdict=decided.verdict, verdict_reason=decided.reason)
    )
    db.execute(
        update(rounds)
        .where(rounds.c.round_id == round_id)
        .values(
            held_out_before=before and before.model_dump(),
            held_out_after=tried.held_out and tried.held_out.model_dump(),
        )
    )
    current = current_version_number(db)
    kept = "Kept" if decided.verdict == Verdict.KEPT else "Rolled back"
    return VerdictResult(
        version=version["number"],
        verdict=decided.verdict,
        reason=decided.reason,
        current_version=current,
        summary=f"{kept} version {version['number']}: {decided.reason}. "
        f"Version {current} is now the current version.",
        scores=VerdictScores(
            held_out_before=before,
            held_out_after=tried.held_out,
            evaluation_after=tried.evaluation,
        ),
    )


@router.post("/api/rounds/{round_id}/model-calls", operation_id="record_improver_call")
def record_improver_call(
    round_id: str, request: ImproverCallRequest, db: Database
) -> Spending:
    """Record one of the improver's model calls, and say what's left to spend."""
    row = open_round(db, round_id)
    db.execute(
        insert(improver_calls).values(
            round_id=round_id, **request.model_dump(), created_at=now()
        )
    )
    return spending_of(db, row)


@router.post("/api/rounds/{round_id}/finish", operation_id="finish_round")
def finish_round(round_id: str, db: Database) -> RoundForService:
    """Finish an open round with nothing waiting for a handler."""
    row = open_round(db, round_id)
    refuse_while_waiting(db, row)
    version = tried_version(db, round_id)
    if version and version["verdict"] is None:
        roll_back(db, version["number"], "the improver didn't evaluate it")
    db.execute(
        update(rounds)
        .where(rounds.c.round_id == round_id)
        .values(status=RoundStatus.FINISHED, finished_at=now())
    )
    return for_the_service(db, round_row(db, round_id))


# The dashboard's operations.


@router.get("/api/improvement", operation_id="get_improvement")
def get_improvement(db: Database) -> Improvement:
    """Get the open or newest round in full, every round, and the recipe's versions."""
    return improvement_page(db)


@router.get("/api/improvement/recipes/{number}", operation_id="get_recipe")
def get_recipe(number: int, db: Database) -> RecipeDetails:
    """Get one version of the improver's recipe, with its diff from the one before."""
    query = select(recipes).where(recipes.c.number == number)
    row = db.execute(query).mappings().first()
    if row is None:
        raise HTTPException(404, f"Recipe {number} not found")
    changes = recipe_diff(db, row)
    return RecipeDetails(
        **recipe_summary(row, current_recipe(db)["number"], changes).model_dump(),
        recipe=row["recipe"],
        diff=changes,
    )


@router.post("/api/improvement/rounds", operation_id="start_round", status_code=202)
def start_round(handler: StartsRounds, db: Database) -> Accepted:
    """Ask the agent's service to start a round of the improver."""
    refuse_while_a_round_is_open(db)
    agent_service.start_round(handler.handler_id)
    return Accepted()


@router.post("/api/improvement/rounds/{round_id}/stop", operation_id="stop_round")
def stop_round(round_id: str, handler: StopsRounds, db: Database) -> RoundSummary:
    """Stop an open round; a version it hadn't given a verdict is rolled back."""
    row = open_round(db, round_id)
    stop(db, row, handler.name, f"Stopped by {handler.name}")
    return summary_of(db, round_row(db, round_id))


@router.post(
    "/api/improvement/rounds/{round_id}/proposals/{proposal_id}/approval",
    operation_id="approve_proposal",
    status_code=202,
)
def approve_proposal(
    round_id: str, proposal_id: str, handler: ReviewsProposals, db: Database
) -> Accepted:
    """Approve the proposal waiting, which the agent's service records and acts on."""
    the_one_waiting(db, open_round(db, round_id), proposal_id)
    agent_service.review_proposal(
        round_id, proposal_id, Review.APPROVED, handler.handler_id, ""
    )
    return Accepted()


@router.post(
    "/api/improvement/rounds/{round_id}/proposals/{proposal_id}/rejection",
    operation_id="reject_proposal",
    status_code=202,
)
def reject_proposal(
    round_id: str,
    proposal_id: str,
    request: RejectionRequest,
    handler: ReviewsProposals,
    db: Database,
) -> Accepted:
    """Reject the proposal waiting, with the reason the improver reads."""
    the_one_waiting(db, open_round(db, round_id), proposal_id)
    agent_service.review_proposal(
        round_id, proposal_id, Review.REJECTED, handler.handler_id, request.reason
    )
    return Accepted()
