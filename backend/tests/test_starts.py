"""Starting dispatches and evaluations, which the backend asks the agent for and
records nothing of."""

import pytest

from backend.database import runs
from backend.tests.rows import count
from backend.tests.sign_in import MARCUS, signed_in


def start_dispatch(client, agents):
    return client.post(
        "/api/dispatches", json={"agents": agents}, headers=signed_in(MARCUS)
    )


def start_evaluation(client, evaluation_set="held_out", tiny=True, agents=5):
    return client.post(
        "/api/evaluations",
        json={"evaluation_set": evaluation_set, "tiny": tiny, "agents": agents},
        headers=signed_in(MARCUS),
    )


def test_start_a_dispatch(client, agent_calls):
    response = start_dispatch(client, 7)
    assert response.status_code == 202
    assert response.json() == {"status": "accepted"}
    assert agent_calls == [{"operation": "start_dispatch", "agents": 7}]
    assert count(runs) == 0


@pytest.mark.parametrize("agents", [0, 26])
def test_a_dispatch_has_1_to_25_claim_agents(client, agent_calls, agents):
    assert start_dispatch(client, agents).status_code == 422
    assert agent_calls == []


def test_start_an_evaluation(client, agent_calls):
    response = start_evaluation(client, "evaluation", False, 25)
    assert response.status_code == 202
    assert agent_calls == [
        {
            "operation": "start_evaluation",
            "evaluation_set": "evaluation",
            "tiny": False,
            "agents": 25,
        }
    ]
    assert count(runs) == 0


@pytest.mark.parametrize(
    ("evaluation_set", "agents"), [("harder", 5), ("held_out", 0), ("held_out", 26)]
)
def test_an_evaluation_needs_a_known_set_and_1_to_25_agents(
    client, agent_calls, evaluation_set, agents
):
    assert start_evaluation(client, evaluation_set, agents=agents).status_code == 422
    assert agent_calls == []
