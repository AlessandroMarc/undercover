"""Finding a run and a version, and the messages for what isn't found, which more
than one of the backend's routers need."""

from fastapi import HTTPException
from sqlalchemy import Connection, RowMapping, func, select

from backend.database import runs, versions
from backend.models import Verdict

RUN_NOT_FOUND = "Run {run_id} not found"
CLAIM_NOT_FOUND = "Claim {claim_id} not found"
VERSION_NOT_FOUND = "Version {number} not found"


def run_row(db: Connection, run_id: str) -> RowMapping:
    """Return one run's row, or raise a 404."""
    row = db.execute(select(runs).where(runs.c.run_id == run_id)).mappings().first()
    if row is None:
        raise HTTPException(404, RUN_NOT_FOUND.format(run_id=run_id))
    return row


def version_row(db: Connection, number: int) -> RowMapping:
    """Return one version of the claim agent's configuration, or raise a 404."""
    query = select(versions).where(versions.c.number == number)
    row = db.execute(query).mappings().first()
    if row is None:
        raise HTTPException(404, VERSION_NOT_FOUND.format(number=number))
    return row


def current_version_number(db: Connection) -> int:
    """Return the current version: the newest one the business's rule kept, which
    is version 1 until a round keeps another."""
    query = select(func.max(versions.c.number)).where(
        versions.c.verdict == Verdict.KEPT
    )
    return db.execute(query).scalar_one()
