"""Fixtures for the backend's and the agent's tests."""

import json

import httpx
import jwt
import pytest
from fastapi.testclient import TestClient

from backend import agent_service, auth
from backend.database import engine, seed
from backend.main import app
from backend.tests.sign_in import PUBLIC_KEYS, SUPABASE_URL


@pytest.fixture(autouse=True)
def database(tmp_path, monkeypatch):
    """Give every test its own freshly seeded SQLite database, never Postgres."""
    path = tmp_path / "undercover.db"
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("UNDERCOVER_DB", str(path))
    seed(engine())
    return path


@pytest.fixture(autouse=True)
def supabase_keys(monkeypatch):
    """Check sign-ins against the tests' own public key, in place of fetching
    Supabase's."""
    monkeypatch.setenv("VITE_SUPABASE_URL", SUPABASE_URL)
    monkeypatch.setattr(jwt.PyJWKClient, "fetch_data", lambda _: PUBLIC_KEYS)
    auth.public_keys.cache_clear()


@pytest.fixture
def agent_answers(monkeypatch):
    """Answer the backend's calls to the agent's service with a handler of the test's
    own, in place of the service."""

    def answer_with(handler):
        transport = httpx.MockTransport(handler)
        stand_in = httpx.Client(
            base_url=agent_service.agent.base_url, transport=transport
        )
        monkeypatch.setattr(agent_service, "agent", stand_in)

    return answer_with


@pytest.fixture(autouse=True)
def agent_calls(agent_answers):
    """Stand in for the agent's service, keeping the path and the body of each call
    to it, or None for a call with no body."""
    calls: list[tuple[str, object]] = []

    def accept(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        calls.append((request.url.path, body))
        return httpx.Response(202, json={"status": "accepted"})

    agent_answers(accept)
    return calls


@pytest.fixture
def client():
    return TestClient(app)
