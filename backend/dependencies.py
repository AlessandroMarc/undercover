"""The FastAPI dependencies the backend's routers share: the database, and the
handler signed in."""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import Connection, select

from backend import auth
from backend.database import engine, handlers
from backend.models import Handler

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
