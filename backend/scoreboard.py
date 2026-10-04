"""Reading runs: a run's claims with their cost and time, an evaluation scored
against the handlers' decisions, and a version's scores from the evaluations its
rounds ran on it."""

from datetime import datetime
from statistics import fmean
from typing import Any

from sqlalchemy import Connection, RowMapping, func, select

from backend import scoring
from backend.database import (
    claim_view,
    claims,
    handler_decisions,
    model_calls,
    run_claims,
    runs,
    work_times,
)
from backend.models import (
    EvaluationSet,
    Measures,
    RunClaim,
    RunKind,
    RunStatus,
    ScoredClaim,
    ScoredEvaluation,
    VersionScores,
)
from backend.views import to_summary

Expected = dict[tuple[str, str], scoring.Answer]


def claims_of(db: Connection, run_id: str) -> list[RowMapping]:
    """Return the rows of a run's claims, in order, with each one's model cost, its
    seconds of work and the start of its first spell in this run."""
    cost = (
        select(model_calls.c.claim_id, func.sum(model_calls.c.cost).label("cost"))
        .where(model_calls.c.run_id == run_id)
        .group_by(model_calls.c.claim_id)
        .subquery()
    )
    spells = (
        select(
            work_times.c.claim_id,
            func.min(work_times.c.started_at).label("first_started_at"),
            func.sum(work_times.c.seconds).label("seconds"),
        )
        .where(work_times.c.run_id == run_id)
        .group_by(work_times.c.claim_id)
        .subquery()
    )
    query = (
        claim_view.add_columns(
            func.coalesce(cost.c.cost, 0).label("model_cost"),
            spells.c.first_started_at,
            func.coalesce(spells.c.seconds, 0).label("seconds"),
        )
        .join(run_claims, run_claims.c.claim_id == claims.c.claim_id)
        .outerjoin(cost, cost.c.claim_id == claims.c.claim_id)
        .outerjoin(spells, spells.c.claim_id == claims.c.claim_id)
        .where(run_claims.c.run_id == run_id)
        .order_by(run_claims.c.position)
    )
    return list(db.execute(query).mappings())


def to_run_claim(row: RowMapping) -> RunClaim:
    """Build a run's claim: its line in the queue, and its cost and time in the run."""
    return RunClaim(
        **to_summary(row).model_dump(),
        started_at=row["first_started_at"],
        seconds=row["seconds"],
        model_cost=row["model_cost"],
    )


def seconds_between(started_at: str, finished_at: str | None) -> float | None:
    """Return the seconds from a start to a finish, or nothing before the finish."""
    if finished_at is None:
        return None
    start, finish = map(datetime.fromisoformat, (started_at, finished_at))
    return (finish - start).total_seconds()


def cost_and_time(db: Connection, row: RowMapping) -> dict[str, Any]:
    """Return a run's model cost in all, and its seconds once it has finished."""
    total = select(func.coalesce(func.sum(model_calls.c.cost), 0)).where(
        model_calls.c.run_id == row["run_id"]
    )
    return {
        "model_cost": db.execute(total).scalar_one(),
        "seconds": seconds_between(row["started_at"], row["finished_at"]),
    }


def scored_claim(row: RowMapping, expected: scoring.Answer) -> ScoredClaim:
    """Put an evaluation's copy beside the handler's decision on its original."""
    answer = scoring.answer_of(row["decision"], row["payout"])
    return ScoredClaim(
        **to_run_claim(row).model_dump(),
        copy_of=row["copy_of"],
        reason=row["reason"],
        handler_decision=expected.decision,
        handler_payout=expected.payout,
        right=scoring.is_right(answer, expected),
        mistake_cost=scoring.mistake_cost(answer, expected),
    )


def expected_answers(db: Connection) -> Expected:
    """Return the handlers' decisions on every labeled claim, by set and claim."""
    rows = db.execute(select(handler_decisions)).mappings()
    return {
        (d["evaluation_set"], d["claim_id"]): scoring.Answer(d["decision"], d["payout"])
        for d in rows
    }


def score(db: Connection, row: RowMapping, expected: Expected) -> ScoredEvaluation:
    """Score an evaluation from its copies as they stand and the handlers'
    decisions on their originals."""
    scored = [
        scored_claim(claim, expected[row["evaluation_set"], claim["copy_of"]])
        for claim in claims_of(db, row["run_id"])
    ]
    run = cost_and_time(db, row)
    return ScoredEvaluation(
        **row,
        **run,
        size=len(scored),
        measures=scoring.measures(scored, run["model_cost"], run["seconds"]),
        claims=scored,
    )


def average(measures: list[Measures]) -> Measures | None:
    """Average the measures of several runs, or nothing when there are none."""
    if not measures:
        return None
    return Measures(
        **{
            name: fmean(getattr(m, name) for m in measures)
            for name in Measures.model_fields
        }
    )


def version_scores(db: Connection, number: int, expected: Expected) -> VersionScores:
    """A version's scores on each set: the averages of the finished whole-set
    evaluations that rounds ran on it. The Scoreboard's own evaluations and any
    stopped evaluation don't count."""
    query = select(runs).where(
        runs.c.version == number,
        runs.c.kind == RunKind.EVALUATION,
        runs.c.round_id.is_not(None),
        runs.c.status == RunStatus.FINISHED,
        runs.c.tiny.is_(False),
    )
    measures: dict[str, list[Measures]] = {s: [] for s in EvaluationSet}
    for row in db.execute(query).mappings():
        measures[row["evaluation_set"]].append(score(db, row, expected).measures)
    return VersionScores(
        evaluation=average(measures[EvaluationSet.EVALUATION]),
        held_out=average(measures[EvaluationSet.HELD_OUT]),
    )
