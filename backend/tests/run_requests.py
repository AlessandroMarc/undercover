"""Requests the backend's tests send to start runs, as a handler does, to record
their work, as the agent does, and to read them, as the dashboard does."""

from backend.tests.dashboard_reads import read
from backend.tests.rows import newest_run
from backend.tests.sign_in import DANA, signed_in


def started_run(client, started):
    """The run a start created, as the agent reads it, or the start's refusal."""
    if started.status_code != 202:
        return started
    return client.get(f"/api/runs/{newest_run()}")


def create_dispatch(client, agents=3):
    """Start a dispatch as a handler does, which the app creates, and return it."""
    started = client.post(
        "/api/dispatches", json={"agents": agents}, headers=signed_in(DANA)
    )
    return started_run(client, started)


def dispatch_of(client, *claim_ids):
    """Create a dispatch and record its claims, and return its id."""
    run_id = create_dispatch(client).json()["run_id"]
    record_claims(client, run_id, *claim_ids)
    return run_id


def record_claims(client, run_id, *claim_ids):
    return client.put(f"/api/runs/{run_id}/claims", json={"claim_ids": claim_ids})


def finish(client, run_id):
    return client.post(f"/api/runs/{run_id}/finish")


def latest_dispatch(client):
    return read(client, "/api/dispatches/latest").json()


def create_evaluation(client, evaluation_set="held_out", tiny=True, agents=5):
    """Start an evaluation as a handler does, which the app creates with its
    copies, and return it."""
    started = client.post(
        "/api/evaluations",
        json={"evaluation_set": evaluation_set, "tiny": tiny, "agents": agents},
        headers=signed_in(DANA),
    )
    return started_run(client, started)


def get_evaluation(client, run_id):
    return read(client, f"/api/evaluations/{run_id}").json()


def queue(client):
    return client.get("/api/claims").json()
