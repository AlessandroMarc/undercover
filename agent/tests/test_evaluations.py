"""Evaluations: the agent's service works copies of a labelled set's claims, and the
backend scores them."""

import threading

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from agent import api, harness, service
from agent.tests.dispatching import dispatch
from agent.tests.queue_setup import leave_waiting
from agent.tests.records import (
    claim_of,
    evaluations,
    latest_dispatch,
    model_calls_of,
    queue,
    work_times_of,
)
from agent.tests.stubs import decide, stub, swarm

TINY = ["CLM-1007", "CLM-1015", "CLM-1017", "CLM-1020", "CLM-1021"]


def test_an_evaluation_through_the_service(client, serve):
    before = queue(client)
    outage = RuntimeError("503: The model is unavailable")
    model = swarm(
        {
            "CLM-1007-E1": decide("approve", 50.0),
            "CLM-1015-E1": decide("approve", 300.0),
            "CLM-1017-E1": decide("decline", 0),
            "CLM-1020-E1": decide("approve", 1240.0),
            "CLM-1021-E1": [outage, outage],
        }
    )
    saver = InMemorySaver()
    response = serve(model, saver).post(
        "/api/evaluations",
        json={"evaluation_set": "evaluation", "tiny": True, "agents": 5},
    )
    assert response.status_code == 202

    [listed] = evaluations(client)
    assert (listed["status"], listed["agents"], listed["size"]) == ("finished", 5, 5)
    assert queue(client) == before
    held = claim_of(client, "CLM-1020-E1")
    assert held["status"] == "waiting_for_sign_off"
    assert saver.get_tuple(harness.thread_of(held)) is None
    paid = claim_of(client, "CLM-1007-E1")
    assert saver.get_tuple(harness.thread_of(paid)) is not None
    assert claim_of(client, "CLM-1021-E1")["status"] == "left_for_handler"

    evaluation = client.get(f"/api/evaluations/{listed['run_id']}").json()
    measures = evaluation["measures"]
    assert (measures["decision_accuracy"], measures["accuracy"]) == (0.4, 0.2)
    assert measures["cost_of_mistakes"] == 2850.0
    assert measures["straight_through"] == 0.8
    copies = [f"{claim_id}-E1" for claim_id in TINY]
    cost = sum(c["cost"] for i in copies for c in model_calls_of(i))
    seconds = sum(w["seconds"] for i in copies for w in work_times_of(i))
    assert measures["model_cost_per_claim"] == pytest.approx(cost / 5)
    assert measures["seconds_per_claim"] == pytest.approx(seconds / 5)
    assert cost == pytest.approx(0.0042 * 8)


def test_a_dispatch_leaves_an_evaluations_copies_alone(client):
    leave_waiting("CLM-1001")
    api.create_evaluation("held_out", True, 5, "stub", "none")
    client.post("/api/claims/CLM-1104-E1/start", json={"thread_id": "copy-thread"})
    dispatch(swarm({"CLM-1001": decide("refer", 0)}))

    assert [c["claim_id"] for c in latest_dispatch(client)["claims"]] == ["CLM-1001"]
    copy = claim_of(client, "CLM-1104-E1")
    assert (copy["status"], copy["thread_id"]) == ("in_progress", "copy-thread")
    assert claim_of(client, "CLM-1106-E1")["status"] == "waiting"


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("/api/dispatches", "/api/evaluations"),
        ("/api/evaluations", "/api/dispatches"),
    ],
)
def test_a_dispatch_and_an_evaluation_never_run_together(
    client, serve, monkeypatch, first, second
):
    leave_waiting()
    working, release = threading.Event(), threading.Event()
    work_run = service.work_run

    def held(run, new_graph, resuming):
        working.set()
        release.wait(5)
        return work_run(run, new_graph, resuming)

    monkeypatch.setattr(service, "work_run", held)
    agent = serve(stub())
    body = {"evaluation_set": "held_out", "tiny": True, "agents": 3}
    running = threading.Thread(target=agent.post, args=(first,), kwargs={"json": body})
    running.start()
    assert working.wait(5)

    refused = agent.post(second, json=body)
    assert refused.status_code == 409
    assert refused.json()["detail"] == "A dispatch or an evaluation is already running"
    release.set()
    running.join(5)
    assert not running.is_alive()


def test_the_agent_cant_read_the_scoreboard():
    for name in (
        "list_evaluations",
        "get_evaluation",
        "start_dispatch",
        "start_evaluation",
    ):
        assert not hasattr(api, name)
