"""What the app knows of the agent's work: how long it may go quiet before it counts
as stopped."""

from datetime import UTC, datetime, timedelta

# The agent says it is still working every minute; work it hasn't spoken of for
# this long counts as stopped.
QUIET = timedelta(minutes=5)


def heard_lately(stamp: str | None) -> bool:
    """Say whether the agent last said it was working within QUIET of now."""
    return (
        stamp is not None and datetime.now(UTC) - datetime.fromisoformat(stamp) < QUIET
    )
