"""The FastAPI dependencies the backend's routers share: the database, the handler
signed in, and the senior handler an action needs."""

from collections.abc import Callable, Iterator
from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import Connection, select

from backend import auth
from backend.database import engine, handlers
from backend.lookups import current_settings
from backend.models import Handler
from backend.money import dollars

NOT_SIGNED_IN = "The sign-in isn't valid. Please sign in again."


def database() -> Iterator[Connection]:
    """Open the database for one request, in a transaction committed at its end."""
    with engine().begin() as connection:
        yield connection


# Committed before the response is sent and before any background task runs.
Database = Annotated[Connection, Depends(database, scope="function")]

# Reads the access token from the Authorization header, and refuses a request
# without one with a 401.
bearer = HTTPBearer()


def signed_in_handler(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer)],
    db: Database,
) -> Handler:
    """Return the handler signed in with the request's token, or raise a 401 when
    the token isn't valid or a 403 when no handler has its email."""
    try:
        email = auth.email_of(credentials.credentials)
    except auth.NotSignedIn as error:
        raise HTTPException(
            401, NOT_SIGNED_IN, headers={"WWW-Authenticate": "Bearer"}
        ) from error
    row = db.execute(select(handlers).where(handlers.c.email == email)).mappings()
    handler = row.first()
    if handler is None:
        raise HTTPException(403, f"{email} isn't one of our claims handlers")
    return Handler(**handler)


SignedIn = Annotated[Handler, Depends(signed_in_handler)]


def senior(action: str) -> Callable[[Handler, Connection], Handler]:
    """Make the dependency for an action only a handler who can sign off payouts
    over the limit may take: it returns the signed-in handler, or raises a 403 that
    names the action and says why."""

    def senior_handler(handler: SignedIn, db: Database) -> Handler:
        refuse_unless_senior(db, handler, action)
        return handler

    return senior_handler


def refuse_unless_senior(db: Connection, handler: Handler, action: str) -> None:
    """Raise a 403 that names the action and says why, unless the handler can sign
    off payouts over the limit."""
    if not handler.can_approve_over_limit:
        limit = dollars(current_settings(db).approval_limit)
        raise HTTPException(
            403,
            f"Only a handler who can sign off payouts over {limit} can {action}. "
            f"{handler.name} can't.",
        )
