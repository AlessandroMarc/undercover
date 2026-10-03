"""Fixtures for the backend's and the agent's tests."""

import pytest
from fastapi.testclient import TestClient

from backend.database import engine, seed
from backend.main import app


@pytest.fixture(autouse=True)
def database(tmp_path, monkeypatch):
    """Give every test its own freshly seeded SQLite database, never Postgres."""
    path = tmp_path / "undercover.db"
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("UNDERCOVER_DB", str(path))
    seed(engine())
    return path


@pytest.fixture
def client():
    return TestClient(app)
