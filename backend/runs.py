"""The backend's operations on runs: the dispatches and evaluations the agent's
service works. Only the service writes them, under /api/runs; the dashboard reads
them under /api/dispatches and /api/evaluations."""

import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException
from sqlalchemy import Connection, RowMapping, delete, func, insert, select, update

from backend import agent_service
from backend.database import (
    claim_view,
    claims,
    model_calls,
    now,
    run_claims,
    runs,
    work_times,
)
from backend.dependencies import Database
from backend.models import (
    Accepted,
    DispatchRequest,
    DispatchSummary,
    HeldPayout,
    Run,
    RunClaim,
    RunClaimsRequest,
    StartDispatchRequest,
)
from backend.views import to_summary

RUN_NOT_FOUND = "Run {run_id} not found"
RUNNING, FINISHED, STOPPED = "running", "finished", "stopped"
DISPATCH = "dispatch"
# Claims a dispatch left that the next one picks up.
UNFINISHED = {"in_progress", "waiting"}

router = APIRouter()


def run_row(db: Connection, run_id: str) -> RowMapping:
    """Return one run's row, or raise a 404."""
    row = db.execute(select(runs).where(runs.c.run_id == run_id)).mappings().first()
    if row is None:
        raise HTTPException(404, RUN_NOT_FOUND.format(run_id=run_id))
    return row


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


def find_run(db: Connection, run_id: str) -> Run:
    """Return one run with its claims, its model cost and its time, or raise a 404."""
    row = run_row(db, run_id)
    total = select(func.coalesce(func.sum(model_calls.c.cost), 0)).where(
        model_calls.c.run_id == run_id
    )
    return Run(
        **row,
        claims=[to_run_claim(claim) for claim in claims_of(db, run_id)],
        model_cost=db.execute(total).scalar_one(),
        seconds=seconds_between(row["started_at"], row["finished_at"]),
    )


def running_run(db: Connection, run_id: str) -> RowMapping:
    """Return a run's row if it is still running, or raise a 404 or a 409."""
    row = run_row(db, run_id)
    if row["status"] != RUNNING:
        raise HTTPException(409, f"Run {run_id} is not running")
    return row


def summarize(rows: list[RowMapping]) -> DispatchSummary:
    """Say what a dispatch left, from its claims as they stand, counting each claim
    once: the decisions, with the payouts waiting for a sign-off counted as
    approved, the claims left for a handler, and those the next dispatch picks up."""
    unfinished = [row["claim_id"] for row in rows if row["status"] in UNFINISHED]
    decided = [row for row in rows if row["status"] not in UNFINISHED]
    decisions = [row["decision"] for row in decided]
    return DispatchSummary(
        approved=decisions.count("approve"),
        declined=decisions.count("decline"),
        referred=decisions.count("refer"),
        waiting_for_sign_off=[
            HeldPayout(claim_id=row["claim_id"], payout=row["payout"])
            for row in rows
            if row["status"] == "waiting_for_sign_off"
        ],
        left_for_handler=[
            row["claim_id"] for row in rows if row["status"] == "left_for_handler"
        ],
        unfinished=unfinished,
    )


@router.post("/api/runs/dispatches", operation_id="create_dispatch")
def create_dispatch(request: DispatchRequest, db: Database) -> Run:
    """Record a new dispatch, running, with its claims to come."""
    run_id = str(uuid.uuid4())
    db.execute(
        insert(runs).values(
            run_id=run_id,
            kind=DISPATCH,
            **request.model_dump(),
            status=RUNNING,
            started_at=now(),
        )
    )
    return find_run(db, run_id)


@router.put("/api/runs/{run_id}/claims", operation_id="record_run_claims")
def record_run_claims(run_id: str, request: RunClaimsRequest, db: Database) -> Run:
    """Record the claims a running dispatch works, in order."""
    running_run(db, run_id)
    known = select(claims.c.claim_id).where(claims.c.claim_id.in_(request.claim_ids))
    missing = set(request.claim_ids) - set(db.execute(known).scalars())
    if missing:
        raise HTTPException(404, f"Claim {min(missing)} not found")
    db.execute(delete(run_claims).where(run_claims.c.run_id == run_id))
    if request.claim_ids:
        db.execute(
            insert(run_claims),
            [
                {"run_id": run_id, "position": position, "claim_id": claim_id}
                for position, claim_id in enumerate(request.claim_ids)
            ],
        )
    return find_run(db, run_id)


@router.post("/api/runs/{run_id}/finish", operation_id="finish_run")
def finish_run(run_id: str, db: Database) -> Run:
    """Finish a running run; a dispatch gets its summary from its claims as they are."""
    row = running_run(db, run_id)
    summary = None
    if row["kind"] == DISPATCH:
        summary = summarize(claims_of(db, run_id)).model_dump()
    db.execute(
        update(runs)
        .where(runs.c.run_id == run_id)
        .values(status=FINISHED, finished_at=now(), summary=summary)
    )
    return find_run(db, run_id)


@router.post("/api/runs/stop", operation_id="stop_runs")
def stop_runs(db: Database) -> list[str]:
    """Mark every running run stopped, as the agent's service does when it starts."""
    query = (
        update(runs)
        .where(runs.c.status == RUNNING)
        .values(status=STOPPED)
        .returning(runs.c.run_id)
    )
    return list(db.execute(query).scalars())


@router.get("/api/dispatches/latest", operation_id="get_latest_dispatch")
def get_latest_dispatch(db: Database) -> Run | None:
    """Get the newest dispatch with its claims, cost, time and summary, or nothing."""
    query = (
        select(runs.c.run_id)
        .where(runs.c.kind == DISPATCH)
        .order_by(runs.c.number.desc())
        .limit(1)
    )
    run_id = db.execute(query).scalar_one_or_none()
    return None if run_id is None else find_run(db, run_id)


@router.post("/api/dispatches", operation_id="start_dispatch", status_code=202)
def start_dispatch(request: StartDispatchRequest) -> Accepted:
    """Ask the agent's service to start a dispatch with up to N claim agents at once."""
    agent_service.start_dispatch(request.agents)
    return Accepted(status="accepted")
