"""What the backend has recorded, read and written straight in its tables."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import Table, func, select, update

from backend.calculation import keep_calculation
from backend.database import claim_view, claims, engine, stamp
from backend.models import CalculationStep, Payout


def count(table: Table) -> int:
    """How many rows a table holds."""
    with engine().connect() as db:
        return db.execute(select(func.count()).select_from(table)).scalar_one()


def calculated(claim_id: str, payout: float) -> None:
    """Keep a calculation of a payout for a started claim's current attempt, as
    calculate_payout keeps one."""
    with engine().begin() as db:
        query = select(claims.c.thread_id).where(claims.c.claim_id == claim_id)
        thread_id = db.execute(query).scalar_one()
        steps = [CalculationStep(step="The covered costs", amount=payout)]
        worked_out = Payout(calculation=steps, payout=payout, needs_sign_off=False)
        keep_calculation(db, claim_id, thread_id, worked_out)


def resume_heard(claim_id: str, ago: timedelta) -> None:
    """Set when the agent last said a resume was working on a claim."""
    moment = stamp(datetime.now(UTC) - ago)
    with engine().begin() as db:
        db.execute(
            update(claims)
            .where(claims.c.claim_id == claim_id)
            .values(resume_heard_at=moment)
        )


def committed_claim(claim_id: str):
    """A claim's row as another connection reads it: what has been committed."""
    with engine().connect() as db:
        query = claim_view.where(claims.c.claim_id == claim_id)
        return db.execute(query).mappings().one()
