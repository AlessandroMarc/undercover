"""The backend's operations on the claim agent's configuration: its versions, for the
claim agent and for the Configuration page."""

from fastapi import APIRouter
from sqlalchemy import Connection, RowMapping, select

from backend.database import versions
from backend.dependencies import Database
from backend.diffs import diff
from backend.documents import contents
from backend.lookups import current_version_number, version_row
from backend.models import (
    ClaimAgentVersion,
    Configuration,
    VersionDetails,
    VersionScores,
    VersionStatus,
    VersionSummary,
)
from backend.scoreboard import expected_answers, version_scores

router = APIRouter()


def with_contents(db: Connection, instructions: str) -> str:
    """The claim agent's instructions as it reads them: they end with the contents
    of the policy wording and the claims manual."""
    return f"{instructions}\n{contents(db)}"


def for_the_claim_agent(db: Connection, row: RowMapping) -> ClaimAgentVersion:
    """A version as the claim agent reads it, with no scores."""
    return ClaimAgentVersion(
        number=row["number"],
        instructions=with_contents(db, row["instructions"]),
        model=row["model"],
        reasoning_effort=row["reasoning_effort"],
    )


def status_of(row: RowMapping, current: int) -> VersionStatus:
    """Say where a version stands: current, kept, rolled back or under test."""
    if row["number"] == current:
        return VersionStatus.CURRENT
    if row["verdict"] is None:
        return VersionStatus.UNDER_TEST
    return VersionStatus(row["verdict"])


def summary_of(
    row: RowMapping,
    before: RowMapping | None,
    current: int,
    scores: VersionScores,
) -> VersionSummary:
    """A version with what it changed from the version it was based on, if any,
    where it stands and its scores."""
    changes = diff(before["instructions"], row["instructions"]) if before else None
    return VersionSummary(
        **row,
        status=status_of(row, current),
        model_before=before["model"] if before else None,
        reasoning_effort_before=before["reasoning_effort"] if before else None,
        lines_added=changes.added if changes else 0,
        lines_removed=changes.removed if changes else 0,
        scores=scores,
    )


@router.get("/api/versions/current", operation_id="get_current_version")
def get_current_version(db: Database) -> ClaimAgentVersion:
    """Get the current version of the claim agent: its instructions and its model."""
    return for_the_claim_agent(db, version_row(db, current_version_number(db)))


@router.get("/api/versions/{number}", operation_id="get_version")
def get_version(number: int, db: Database) -> ClaimAgentVersion:
    """Get one version of the claim agent: its instructions and its model."""
    return for_the_claim_agent(db, version_row(db, number))


@router.get("/api/configuration", operation_id="get_configuration")
def get_configuration(db: Database) -> Configuration:
    """Get the claim agent's versions, newest first, with what each changed."""
    current = current_version_number(db)
    query = select(versions).order_by(versions.c.number.desc())
    rows = {row["number"]: row for row in db.execute(query).mappings()}
    expected = expected_answers(db)
    return Configuration(
        current=current,
        versions=[
            summary_of(
                row,
                rows.get(row["based_on"]),
                current,
                version_scores(db, number, expected),
            )
            for number, row in rows.items()
        ],
    )


@router.get("/api/configuration/versions/{number}", operation_id="get_version_details")
def get_version_details(number: int, db: Database) -> VersionDetails:
    """Get one version in full, with its diff from the version it was based on."""
    row = version_row(db, number)
    before = version_row(db, row["based_on"]) if row["based_on"] else None
    scores = version_scores(db, number, expected_answers(db))
    summary = summary_of(row, before, current_version_number(db), scores)
    return VersionDetails(
        **summary.model_dump(),
        instructions=with_contents(db, row["instructions"]),
        diff=diff(before["instructions"], row["instructions"]) if before else None,
    )
