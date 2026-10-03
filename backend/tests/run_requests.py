"""Requests the backend's tests send to record runs, as the agent's service does."""


def create_dispatch(client, agents=3):
    return client.post(
        "/api/runs/dispatches",
        json={
            "agents": agents,
            "model": "openai/gpt-6-luna",
            "reasoning_effort": "low",
        },
    )


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
    return client.get("/api/dispatches/latest").json()
