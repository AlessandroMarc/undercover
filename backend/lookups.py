"""Finding a run, and the messages for a run or a claim not found, which both of
the backend's routers need."""

from fastapi import HTTPException
from sqlalchemy import Connection, RowMapping, select

from backend.database import runs

RUN_NOT_FOUND = "Run {run_id} not found"
CLAIM_NOT_FOUND = "Claim {claim_id} not found"


def run_row(db: Connection, run_id: str) -> RowMapping:
    """Return one run's row, or raise a 404."""
    row = db.execute(select(runs).where(runs.c.run_id == run_id)).mappings().first()
    if row is None:
        raise HTTPException(404, RUN_NOT_FOUND.format(run_id=run_id))
    return row
