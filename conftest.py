"""Fixtures for the backend's and the agent's tests."""

import pytest
from fastapi.testclient import TestClient

from backend.database import seed
from backend.main import app


@pytest.fixture(autouse=True)
def database(tmp_path, monkeypatch):
    """Give every test its own freshly seeded database."""
    path = tmp_path / "undercover.db"
    monkeypatch.setenv("UNDERCOVER_DB", str(path))
    seed(path)
    return path


@pytest.fixture
def client():
    return TestClient(app)
