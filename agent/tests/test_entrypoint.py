"""The agent's AgentCore app: it gets ready on its first request, reads each payload,
checks the key off Runtime, and starts each operation's work on a thread of its own,
which its /ping reports as busy until it ends."""

import importlib
import os
import random
import socket
import sys
import threading
from functools import partial
from typing import cast

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from agent import api, entrypoint, harness, identity
from agent.tests.dispatching import new_dispatch
from agent.tests.held import StopAtThePause, hold, resume_claim
from agent.tests.invoking import ACCEPTED, HEALTH, start_dispatch
from agent.tests.queue_setup import leave_waiting
from agent.tests.records import claim_of, model_calls_of, work_times_of
from agent.tests.stubs import agent_on, approve, decide, stub, swarm
from backend.tests.claim_requests import sign_off
from backend.tests.dashboard_reads import evaluations
from backend.tests.run_requests import latest_dispatch
from backend.tests.versions import add_version

# The settings the deployment gives the agent on Runtime, naming the providers of
# its three credentials in AgentCore Identity.
CREDENTIALS = {
    "OPENROUTER_API_KEY": "undercover-openrouter",
    "UNDERCOVER_API_KEY": "undercover-api-key",
    "DATABASE_URL": "undercover-database",
}


def refuse(*args, **kwargs):
    raise ConnectionRefusedError("Nothing may connect as the agent is imported")


def test_importing_the_agent_reads_no_setting_opens_nothing_and_starts_nothing(
    monkeypatch,
):
    for name in list(os.environ):
        if name != "PATH":
            monkeypatch.delenv(name)
    for setting, provider in CREDENTIALS.items():
        monkeypatch.setenv(f"AGENTCORE_CREDENTIAL_{setting}_NAME", provider)
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    for name in list(sys.modules):
        if name.split(".")[0] in ("agent", "runtime"):
            monkeypatch.delitem(sys.modules, name)
    threads = set(threading.enumerate())

    main = importlib.import_module("runtime.main")
    assert main.app is sys.modules["agent.entrypoint"].app
    assert set(threading.enumerate()) <= threads


@pytest.fixture
def on_runtime(monkeypatch, agent_key):
    """Run as on AgentCore Runtime: the deployment names the three credentials, and
    a stand-in for Identity gives each provider's value, keeping each it was asked
    for."""
    asked = []
    for setting, provider in CREDENTIALS.items():
        monkeypatch.setenv(f"AGENTCORE_CREDENTIAL_{setting}_NAME", provider)

    # The database's value is empty, which keeps the tests' backend, in the same
    # process, on SQLite.
    values = {
        "undercover-openrouter": "openrouter-key",
        "undercover-api-key": agent_key,
        "undercover-database": "",
    }

    def requires_api_key(provider_name):
        def wrap(function):
            def fetched():
                asked.append(provider_name)
                return function(api_key=values[provider_name])

            return fetched

        return wrap

    monkeypatch.setattr(identity, "requires_api_key", requires_api_key)
    return asked


def test_on_runtime_the_first_request_fetches_each_credential_once(
    on_runtime, workers_from, fresh_agent, monkeypatch, agent_key
):
    opened, reseeded = [], []
    workers_from(stub(), InMemorySaver(), stub())
    monkeypatch.setattr(entrypoint, "open_checkpoint_pool", lambda: opened.append(1))
    monkeypatch.setattr(random, "seed", lambda: reseeded.append(opened.copy()))
    for setting in CREDENTIALS:
        monkeypatch.delenv(setting, raising=False)

    agent = fresh_agent()
    assert agent.invoke(HEALTH, headers={}).json() == {"healthy": True}
    assert sorted(on_runtime) == sorted(CREDENTIALS.values())
    assert os.environ["UNDERCOVER_API_KEY"] == agent_key
    assert os.environ["OPENROUTER_API_KEY"] == "openrouter-key"
    assert os.environ["DATABASE_URL"] == ""
    assert (reseeded, opened) == ([[]], [1])

    assert agent.invoke(HEALTH, headers={}).json() == {"healthy": True}
    assert len(on_runtime) == 3
    assert opened == [1]


def test_on_runtime_a_request_needs_no_key(on_runtime, serve):
    leave_waiting()
    agent = serve(stub())
    accepted = agent.invoke(start_dispatch(3), headers={})
    assert (accepted.status_code, accepted.json()) == (200, ACCEPTED)


def test_a_failure_to_get_ready_answers_503_and_the_next_request_tries_again(
    workers_from, fresh_agent, monkeypatch
):
    workers_from(stub(), InMemorySaver(), stub())

    def unreachable():
        raise ConnectionError("Supabase isn't answering")

    monkeypatch.setattr(entrypoint, "open_checkpoint_pool", unreachable)
    agent = fresh_agent()
    failed = agent.invoke(HEALTH)
    assert (failed.status_code, failed.json()) == (
        503,
        {"error": "The agent couldn't get ready: ConnectionError: Supabase isn't "
         "answering"},
    )  # fmt: skip
    monkeypatch.setattr(entrypoint, "open_checkpoint_pool", object)
    assert agent.invoke(HEALTH).json() == {"healthy": True}


def test_getting_ready_needs_the_agents_key(workers_from, fresh_agent, monkeypatch):
    workers_from(stub(), InMemorySaver(), stub())
    monkeypatch.delenv("UNDERCOVER_API_KEY")
    failed = fresh_agent().invoke(HEALTH, headers={})
    assert failed.status_code == 503
    assert "UNDERCOVER_API_KEY is missing" in failed.json()["error"]


def test_the_health_check_needs_no_key(serve):
    agent = serve(stub())
    healthy = agent.invoke(HEALTH, headers={})
    assert (healthy.status_code, healthy.json()) == (200, {"healthy": True})


@pytest.mark.parametrize(
    "headers",
    [{}, {"Authorization": "Bearer not-the-key"}, {"Authorization": "the-key"}],
)
def test_off_runtime_a_request_without_the_key_is_refused(client, serve, headers):
    agent = serve(stub())
    refused = agent.invoke(start_dispatch(3), headers=headers)
    assert (refused.status_code, refused.json()) == (
        401,
        {"error": "This needs the agent's API key"},
    )
    assert latest_dispatch(client) is None


@pytest.mark.parametrize(
    ("payload", "error"),
    [
        ({"operation": "dance"}, "Unknown operation: dance"),
        ({"agents": 3}, "The payload names no operation"),
        ([{"operation": "health"}], "The payload isn't a JSON object"),
        ({"operation": "start_dispatch"}, "agents: Field required"),
        (
            {"operation": "start_dispatch", "agents": "3"},
            "agents: Input should be a valid integer",
        ),
        (
            {
                "operation": "start_evaluation",
                "agents": 5,
                "evaluation_set": "held_out",
                "tiny": "yes",
            },
            "tiny: Input should be a valid boolean",
        ),
        (
            {"operation": "start_dispatch", "agents": 3, "tiny": True},
            "tiny: Extra inputs are not permitted",
        ),
        (
            {"operation": "start_dispatch", "agents": 26},
            "agents: Input should be less than or equal to 25",
        ),
        (
            {"operation": "start_dispatch", "agents": 0},
            "agents: Input should be greater than or equal to 1",
        ),
        (
            {"operation": "resume_claim"},
            "claim_id: Field required",
        ),
    ],
)
def test_a_payload_it_cant_read_gets_a_400_saying_why(client, serve, payload, error):
    refused = serve(stub()).invoke(payload)
    assert (refused.status_code, refused.json()) == (400, {"error": error})
    assert latest_dispatch(client) is None


def test_start_a_dispatch(client, serve):
    ids = ["CLM-1001", "CLM-1003", "CLM-1004"]
    leave_waiting(*ids)
    model = swarm({claim_id: decide("refer", 0) for claim_id in ids}, pause=0.05)
    response = serve(model).invoke(start_dispatch(2))
    assert (response.status_code, response.json()) == (200, ACCEPTED)

    dispatch = latest_dispatch(client)
    assert (dispatch["status"], dispatch["agents"]) == ("finished", 2)
    assert (dispatch["version"], dispatch["model"]) == (1, "openai/gpt-6-luna")
    assert [c["status"] for c in dispatch["claims"]] == ["decided"] * 3
    assert model.most_at_once == 2


TINY_HELD_OUT = ["CLM-1104", "CLM-1106", "CLM-1110", "CLM-1112", "CLM-1114"]


def test_start_an_evaluation(client, serve):
    model = swarm({f"{c}-E1": decide("refer", 0) for c in TINY_HELD_OUT})
    payload = {
        "operation": "start_evaluation",
        "agents": 5,
        "evaluation_set": "held_out",
        "tiny": True,
    }
    assert serve(model).invoke(payload).json() == ACCEPTED
    [evaluation] = evaluations(client)
    assert (evaluation["status"], evaluation["size"], evaluation["agents"]) == (
        "finished",
        5,
        5,
    )


def test_ping_is_busy_while_work_goes_on_and_healthy_once_it_ends(
    client, serve, held_run
):
    leave_waiting()
    agent = serve(stub())
    assert agent.ping() == "Healthy"
    assert agent.invoke(start_dispatch(3), wait=False).json() == ACCEPTED
    assert held_run.working.wait(5)
    assert agent.ping() == "HealthyBusy"
    held_run.release.set()
    agent.settle()
    assert latest_dispatch(client)["status"] == "finished"


def test_ping_is_healthy_after_work_that_raised(client, serve, monkeypatch):
    saver = InMemorySaver()
    hold(saver=saver)
    sign_off(client, "CLM-1003")

    def broken(claim_id, agent):
        raise RuntimeError("The backend is unreachable")

    monkeypatch.setattr(entrypoint, "resume", broken)
    agent = serve(stub(), saver)
    assert resume_claim(agent, "CLM-1003").json() == ACCEPTED
    assert agent.ping() == "Healthy"


def test_one_run_at_a_time(client, serve, held_run):
    leave_waiting()
    agent = serve(stub())
    assert agent.invoke(start_dispatch(3), wait=False).json() == ACCEPTED
    assert held_run.working.wait(5)

    refused = agent.invoke(start_dispatch(3), wait=False)
    assert (refused.status_code, refused.json()) == (
        200,
        {"refused": "A dispatch is running"},
    )
    for payload in (
        {
            "operation": "start_evaluation",
            "agents": 5,
            "evaluation_set": "held_out",
            "tiny": True,
        },
        {"operation": "start_round", "handler_id": "H-01"},
    ):
        assert agent.invoke(payload, wait=False).json() == {
            "refused": "A dispatch is running"
        }
    assert latest_dispatch(client)["number"] == 1

    held_run.release.set()
    agent.settle()
    assert latest_dispatch(client)["status"] == "finished"
    assert agent.invoke(start_dispatch(3)).json() == ACCEPTED
    assert latest_dispatch(client)["number"] == 2


def test_a_dispatch_whose_dispatcher_fails_is_stopped(client, serve, monkeypatch):
    leave_waiting()
    work_run = entrypoint.work_run

    def broken(run, work):
        raise RuntimeError("The backend is unreachable")

    monkeypatch.setattr(entrypoint, "work_run", broken)
    agent = serve(stub())
    assert agent.invoke(start_dispatch(3)).json() == ACCEPTED
    assert latest_dispatch(client)["status"] == "stopped"

    monkeypatch.setattr(entrypoint, "work_run", work_run)
    assert agent.invoke(start_dispatch(3)).json() == ACCEPTED
    assert latest_dispatch(client)["status"] == "finished"


def test_a_run_whose_context_layer_isnt_answering_stops_with_one_line(
    client, serve, caplog
):
    agent = serve(stub())

    def down(version, kind):
        raise ConnectionError("The context layer isn't answering at http://x/mcp")

    entrypoint.ready.get().claim_agents = down
    assert agent.invoke(start_dispatch(3)).json() == ACCEPTED
    assert latest_dispatch(client)["status"] == "stopped"
    assert "The run stopped: The context layer isn't answering at http://x/mcp" in (
        caplog.messages
    )


def test_getting_ready_stops_the_runs_left_running(client, workers_from, fresh_agent):
    run_id = new_dispatch()["run_id"]
    workers_from(stub(), InMemorySaver(), stub())
    fresh_agent().invoke(HEALTH)
    dispatch = latest_dispatch(client)
    assert (dispatch["run_id"], dispatch["status"]) == (run_id, "stopped")


def test_a_dispatch_works_on_the_current_version(client, serve):
    add_version("Version 2's instructions", verdict="kept")
    leave_waiting("CLM-1001")
    model = swarm({"CLM-1001": decide("refer", 0)})
    assert serve(model).invoke(start_dispatch(3)).json() == ACCEPTED

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
    assert serve(model).invoke(start_dispatch(3)).json() == ACCEPTED
    version_1 = client.get("/api/versions/1").json()["instructions"]
    assert [prompt[0].content for prompt in model.prompts] == [version_1] * 2


def test_the_workers_are_built_on_the_processs_pool(monkeypatch):
    pool = cast(harness.Pool, object())
    monkeypatch.setattr(
        entrypoint, "claim_graphs", lambda version, kind, pool: (version, kind, pool)
    )
    monkeypatch.setattr(entrypoint, "PostgresSaver", lambda on: ("saver", on))
    workers = entrypoint.workers_on(pool)
    assert workers.claim_agents({"number": 2}, "evaluation") == (
        {"number": 2},
        "evaluation",
        pool,
    )
    assert workers.saver == ("saver", pool)


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
    entrypoint.ready.get().claim_agents = built_on(saver, built)
    response = resume_claim(agent, "CLM-1003")
    assert (response.status_code, response.json()) == (200, ACCEPTED)
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
        ("CLM-9999", "Claim CLM-9999 not found"),
    ]:
        refused = resume_claim(agent, claim_id)
        assert (refused.status_code, refused.json()) == (200, {"refused": reason})
    assert claim_of(client, "CLM-1003")["status"] == "waiting_for_sign_off"


def test_a_resume_is_accepted_while_a_dispatch_is_running(client, serve, held_run):
    leave_waiting("CLM-1003")
    saver = InMemorySaver()
    hold(saver=saver)
    sign_off(client, "CLM-1003")
    agent = serve(stub(), saver)
    assert agent.invoke(start_dispatch(3), wait=False).json() == ACCEPTED
    assert held_run.working.wait(5)

    resumed = agent.invoke(
        {"operation": "resume_claim", "claim_id": "CLM-1003"}, wait=False
    )
    assert resumed.json() == ACCEPTED
    held_run.release.set()
    agent.settle()
    assert not harness.paused(claim_of(client, "CLM-1003"), agent_on(stub(), saver))
    assert latest_dispatch(client)["status"] == "finished"
