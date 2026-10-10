import threading
from contextlib import nullcontext
from functools import partial
from types import SimpleNamespace

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver

from agent import api, harness, service
from agent.tests.dispatching import new_dispatch
from agent.tests.held import StopAtThePause, hold
from agent.tests.queue_setup import leave_waiting
from agent.tests.records import claim_of, model_calls_of, work_times_of
from agent.tests.stubs import agent_on, approve, decide, stub, swarm
from api_rules import rule_breaks
from backend.tests.claim_requests import sign_off
from backend.tests.run_requests import latest_dispatch
from backend.tests.versions import add_version


def start_dispatch(agent, agents):
    return agent.post("/api/dispatches", json={"agents": agents})


def test_the_service_follows_the_api_rules():
    assert rule_breaks(service.app.openapi()) == []


def test_health():
    assert TestClient(service.app).get("/api/health").json() == {"status": "ok"}


def test_start_a_dispatch(client, serve):
    ids = ["CLM-1001", "CLM-1003", "CLM-1004"]
    leave_waiting(*ids)
    model = swarm({claim_id: decide("refer", 0) for claim_id in ids}, pause=0.05)
    response = start_dispatch(serve(model), 2)
    assert response.status_code == 202
    assert response.json() == {"status": "accepted"}

    dispatch = latest_dispatch(client)
    assert (dispatch["status"], dispatch["agents"]) == ("finished", 2)
    assert (dispatch["version"], dispatch["model"]) == (1, "openai/gpt-6-luna")
    assert [c["status"] for c in dispatch["claims"]] == ["decided"] * 3
    assert model.most_at_once == 2


@pytest.mark.parametrize("agents", [0, 26])
def test_a_dispatch_has_1_to_25_claim_agents(client, serve, agents):
    assert start_dispatch(serve(stub()), agents).status_code == 422
    assert latest_dispatch(client) is None


def test_one_run_at_a_time(client, serve, held_run):
    leave_waiting()
    agent = serve(stub())
    first = threading.Thread(target=start_dispatch, args=(agent, 3))
    first.start()
    assert held_run.working.wait(5)

    refused = start_dispatch(agent, 3)
    assert refused.status_code == 409
    assert refused.json()["detail"] == "A dispatch is running"
    assert latest_dispatch(client)["number"] == 1

    held_run.release.set()
    first.join(5)
    assert not first.is_alive()
    assert latest_dispatch(client)["status"] == "finished"
    assert start_dispatch(agent, 3).status_code == 202
    assert latest_dispatch(client)["number"] == 2


def test_a_dispatch_whose_dispatcher_fails_is_stopped(client, serve, monkeypatch):
    leave_waiting()
    work_run = service.work_run

    def broken(run, work):
        raise RuntimeError("The backend is unreachable")

    monkeypatch.setattr(service, "work_run", broken)
    agent = serve(stub())
    assert start_dispatch(agent, 3).status_code == 202
    assert latest_dispatch(client)["status"] == "stopped"

    monkeypatch.setattr(service, "work_run", work_run)
    assert start_dispatch(agent, 3).status_code == 202
    assert latest_dispatch(client)["status"] == "finished"


def test_a_run_whose_context_layer_isnt_answering_stops_with_one_line(client, caplog):
    def down(version, kind):
        raise ConnectionError("The context layer isn't answering at http://x/mcp")

    service.app.dependency_overrides[service.claim_agents] = lambda: down
    try:
        assert start_dispatch(TestClient(service.app), 3).status_code == 202
    finally:
        service.app.dependency_overrides.clear()
    assert latest_dispatch(client)["status"] == "stopped"
    assert caplog.messages == [
        "The run stopped: The context layer isn't answering at http://x/mcp"
    ]


def test_starting_the_service_stops_the_runs_left_running(client, monkeypatch):
    run_id = new_dispatch()["run_id"]
    monkeypatch.setattr(service, "checkpoint_pool", lambda: nullcontext(object()))
    with TestClient(service.app):
        dispatch = latest_dispatch(client)
        assert (dispatch["run_id"], dispatch["status"]) == (run_id, "stopped")


def test_a_dispatch_works_on_the_current_version(client, serve):
    add_version("Version 2's instructions", verdict="kept")
    leave_waiting("CLM-1001")
    model = swarm({"CLM-1001": decide("refer", 0)})
    assert start_dispatch(serve(model), 3).status_code == 202

    dispatch = latest_dispatch(client)
    assert (dispatch["version"], dispatch["model"], dispatch["reasoning_effort"]) == (
        2,
        "google/gemini-3.5-flash-lite",
        "minimal",
    )
    version_2 = client.get("/api/versions/2").json()["instructions"]
    assert version_2.startswith("Version 2's instructions\n")
    assert [prompt[0].content for prompt in model.prompts] == [version_2] * 2


def test_a_run_keeps_its_version_when_another_is_kept_meanwhile(
    client, serve, monkeypatch
):
    leave_waiting("CLM-1001")
    create_dispatch = api.create_dispatch

    def then_keep_version_2(agents):
        run = create_dispatch(agents)
        add_version("Version 2's instructions", verdict="kept")
        return run

    monkeypatch.setattr(api, "create_dispatch", then_keep_version_2)
    model = swarm({"CLM-1001": decide("refer", 0)})
    assert start_dispatch(serve(model), 3).status_code == 202
    version_1 = client.get("/api/versions/1").json()["instructions"]
    assert [prompt[0].content for prompt in model.prompts] == [version_1] * 2


def test_claim_agents_are_built_on_the_services_pool(monkeypatch):
    pool = object()
    monkeypatch.setattr(
        service, "claim_graphs", lambda version, kind, pool: (version, kind, pool)
    )
    app = SimpleNamespace(state=SimpleNamespace(pool=pool))
    request = Request({"type": "http", "app": app})
    built = service.claim_agents(request)({"number": 2}, "evaluation")
    assert built == ({"number": 2}, "evaluation", pool)


def test_the_services_operations():
    operations = {
        operation["operationId"]
        for methods in service.app.openapi()["paths"].values()
        for operation in methods.values()
    }
    assert operations == {
        "health",
        "start_dispatch",
        "start_evaluation",
        "start_round",
        "review_proposal",
        "resume_claim",
    }


def resume_claim(agent, claim_id):
    return agent.post(f"/api/claims/{claim_id}/resume")


def built_on(saver, built):
    """Claim agents on a stub model, sharing a saver, that keep the version and the
    kind of run each was built for."""

    def claim_agents(version, kind):
        built.append((version["number"], kind))
        return partial(agent_on, stub(), saver, version)

    return claim_agents


def test_a_signed_off_claim_is_resumed_in_the_background(client, serve):
    add_version("Version 2's instructions", verdict="kept")
    saver = InMemorySaver()
    hold(saver=saver)
    sign_off(client, "CLM-1003")
    calls, times = model_calls_of("CLM-1003"), work_times_of("CLM-1003")
    agent, built = serve(stub(), saver), []
    service.app.dependency_overrides[service.claim_agents] = lambda: built_on(
        saver, built
    )
    response = resume_claim(agent, "CLM-1003")
    assert (response.status_code, response.json()) == (202, {"status": "accepted"})
    assert built == [(2, None)]
    claim = claim_of(client, "CLM-1003")
    assert claim["status"] == "decided"
    assert not harness.paused(claim, agent_on(stub(), saver))
    assert work_times_of("CLM-1003")[: len(times)] == times
    [resumed] = work_times_of("CLM-1003")[len(times) :]
    assert resumed["run_id"] is None
    # A sign-off has already paid the claim, so the resume calls no model.
    assert model_calls_of("CLM-1003") == calls


def test_resume_claim_refuses_a_claim_that_isnt_paused_with_an_answer(client, serve):
    saver = StopAtThePause()
    with pytest.raises(KeyboardInterrupt):
        hold("CLM-1002", 1350.0, saver)
    sign_off(client, "CLM-1002")
    hold(saver=saver)
    harness.work_claim("CLM-1001", None, agent_on(stub(*decide("decline", 0)), saver))
    run_id = api.create_evaluation("evaluation", True, 5)["run_id"]
    copy = agent_on(stub(*approve("CLM-1020", 1240.0)), saver, pauses=False)
    harness.work_in_run("CLM-1020-E1", run_id, lambda: copy)

    agent = serve(stub(), saver)
    for claim_id, reason in [
        ("CLM-1003", "Claim CLM-1003 has no answer from a handler yet"),
        ("CLM-1001", "Claim CLM-1001 isn't paused for a handler"),
        ("CLM-1020-E1", "Claim CLM-1020-E1 isn't paused for a handler"),
        ("CLM-1002", "Claim CLM-1002 isn't paused for a handler"),
    ]:
        refused = resume_claim(agent, claim_id)
        assert (refused.status_code, refused.json()) == (409, {"detail": reason})
    unknown = resume_claim(agent, "CLM-9999")
    assert (unknown.status_code, unknown.json()) == (
        404,
        {"detail": "Claim CLM-9999 not found"},
    )
    assert claim_of(client, "CLM-1003")["status"] == "waiting_for_sign_off"


def test_a_resume_is_accepted_while_a_dispatch_is_running(client, serve, held_run):
    leave_waiting("CLM-1003")
    saver = InMemorySaver()
    hold(saver=saver)
    sign_off(client, "CLM-1003")
    agent = serve(stub(), saver)
    dispatching = threading.Thread(target=start_dispatch, args=(agent, 3))
    dispatching.start()
    assert held_run.working.wait(5)

    assert resume_claim(agent, "CLM-1003").status_code == 202
    assert not harness.paused(claim_of(client, "CLM-1003"), agent_on(stub(), saver))
    held_run.release.set()
    dispatching.join(5)
    assert latest_dispatch(client)["status"] == "finished"
