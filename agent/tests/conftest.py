from typing import Any

import pytest
from fastapi.testclient import TestClient
from langchain_core.callbacks import BaseCallbackHandler
from langgraph.checkpoint.memory import InMemorySaver

from agent import api, dispatcher, harness, service
from agent.tests.stubs import graph_on
from backend.main import app


@pytest.fixture(autouse=True)
def backend(monkeypatch):
    """Send the agent's requests to the test backend, at the same address."""
    test_backend = TestClient(app, base_url=str(api.backend.base_url))
    monkeypatch.setattr(api, "backend", test_backend)


class RecordRoots(BaseCallbackHandler):
    """Stands in for Langfuse's handler, keeping the metadata of each root run."""

    def __init__(self, roots: list[dict[str, Any]]) -> None:
        self.roots = roots

    def on_chain_start(self, serialized, inputs, *, parent_run_id=None, **kwargs):
        if parent_run_id is None:
            self.roots.append(dict(kwargs.get("metadata") or {}))


@pytest.fixture(autouse=True)
def traces(monkeypatch):
    """Keep Langfuse out of the tests, and record the root runs it would trace."""
    roots: list[dict[str, Any]] = []
    monkeypatch.setattr(harness, "CallbackHandler", lambda: RecordRoots(roots))
    return roots


@pytest.fixture(autouse=True)
def no_waits(monkeypatch):
    """Take the waits out of the dispatcher's RetryPolicy, keeping its tries, so the
    tests never sleep through the backoff. Returns the real policy."""
    real = dispatcher.RETRY
    monkeypatch.setattr(
        dispatcher, "RETRY", real._replace(initial_interval=0, jitter=False)
    )
    return real


@pytest.fixture
def serve():
    """Run the agent's service, without its lifespan, with claim agents on a stub
    model whose graphs share a saver."""

    def with_model(model, saver=None):
        saver = saver or InMemorySaver()
        agents = service.ClaimAgents("stub", "none", lambda: graph_on(model, saver))
        service.app.dependency_overrides[service.claim_agents] = lambda: agents
        return TestClient(service.app)

    yield with_model
    service.app.dependency_overrides.clear()
