"""The connection to the UnderCover backend: its address, the one HTTP client, and how
a request is sent and refused. The claim agent's API and the improver's API both send
their requests through it."""

import os
from typing import Any

import httpx

BACKEND_URL = os.getenv("UNDERCOVER_API", "http://127.0.0.1:8000")

# Retries a refused connection for about 7 seconds, while the backend starts.
backend = httpx.Client(
    base_url=f"{BACKEND_URL}/api",
    timeout=30,
    transport=httpx.HTTPTransport(retries=5),
)


class Refused(Exception):
    """The backend refused a request, with its status code and reason."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(f"{status_code}: {detail}")
        self.status_code, self.detail = status_code, detail


def call(method: str, path: str, **request: Any) -> Any:
    """Send one request to the backend and return its JSON, or raise Refused."""
    response = backend.request(method, path, **request)
    if response.is_error:
        raise Refused(response.status_code, response.json()["detail"])
    return response.json()
