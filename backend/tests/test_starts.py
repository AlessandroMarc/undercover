"""Starting dispatches and evaluations, which the backend asks the agent's service for
and records nothing of."""

import json

import httpx
import pytest
from sqlalchemy import func, select

from backend.database import engine, runs

RUNNING = "A dispatch or an evaluation is already running"


def start_dispatch(client, agents):
    return client.post("/api/dispatches", json={"agents": agents})


def runs_recorded():
    with engine().connect() as db:
        return db.execute(select(func.count()).select_from(runs)).scalar_one()


@pytest.fixture
def asked(agent_answers):
    """Accept each start as the agent's service does, keeping its path and body."""
    starts = []

    def accept(request: httpx.Request) -> httpx.Response:
        starts.append((request.url.path, json.loads(request.content)))
        return httpx.Response(202, json={"status": "accepted"})

    agent_answers(accept)
    return starts


def test_start_a_dispatch(client, asked):
    response = start_dispatch(client, 7)
    assert response.status_code == 202
    assert response.json() == {"status": "accepted"}
    assert asked == [("/api/dispatches", {"agents": 7})]
    assert runs_recorded() == 0


def test_the_services_refusal_is_passed_on(client, agent_answers):
    agent_answers(lambda request: httpx.Response(409, json={"detail": RUNNING}))
    response = start_dispatch(client, 3)
    assert response.status_code == 409
    assert response.json()["detail"] == RUNNING


def test_a_service_that_isnt_running(client, agent_answers):
    def unreachable(request):
        raise httpx.ConnectError("Connection refused")

    agent_answers(unreachable)
    response = start_dispatch(client, 3)
    assert response.status_code == 503
    assert response.json()["detail"] == "The agent's service isn't running"
    assert runs_recorded() == 0


@pytest.mark.parametrize("agents", [0, 26])
def test_a_dispatch_has_1_to_25_claim_agents(client, asked, agents):
    assert start_dispatch(client, agents).status_code == 422
    assert asked == []


def test_any_other_failure_of_the_service_is_an_error(client, agent_answers):
    agent_answers(lambda request: httpx.Response(500, text="Internal Server Error"))
    with pytest.raises(httpx.HTTPStatusError):
        start_dispatch(client, 3)


def test_a_service_that_took_the_start_but_didnt_answer_isnt_said_to_be_down(
    client, agent_answers
):
    def slow(request):
        raise httpx.ReadTimeout("Timed out")

    agent_answers(slow)
    with pytest.raises(httpx.ReadTimeout):
        start_dispatch(client, 3)
