import pytest
from fastapi.testclient import TestClient

from agent import main
from backend.main import app


@pytest.fixture(autouse=True)
def backend_in_process(tmp_path, monkeypatch):
    """Point the agent at the backend app, on a database of its own."""
    monkeypatch.setenv("UNDERCOVER_DB", str(tmp_path / "test.db"))
    monkeypatch.setattr(main, "backend", lambda: TestClient(app))


@pytest.fixture
def api():
    with TestClient(app) as client:
        yield client
