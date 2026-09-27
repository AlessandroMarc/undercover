import pytest
from fastapi.testclient import TestClient

from agent import tools
from backend.main import app
from backend.tests.conftest import client, database

__all__ = ["client", "database"]


@pytest.fixture(autouse=True)
def backend(monkeypatch):
    """Send the agent's requests to the test backend."""
    monkeypatch.setattr(tools, "backend", lambda: TestClient(app))
