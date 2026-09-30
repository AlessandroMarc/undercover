import pytest

from backend.tests.test_workflow import decide, start


def fail(client, claim_id, reason="The model timed out"):
    return client.post(f"/api/claims/{claim_id}/failure", json={"reason": reason})


def test_starting_a_claim_counts_the_attempt(client):
    assert client.get("/api/claims/CLM-1004").json()["attempts"] == 0
    assert start(client, "CLM-1004").json()["attempts"] == 1


def test_a_failed_attempt_goes_back_in_the_queue(client):
    start(client, "CLM-1004")
    claim = fail(client, "CLM-1004").json()
    assert (claim["status"], claim["attempts"]) == ("waiting", 1)
    last = client.get("/api/claims/CLM-1004/steps").json()[-1]
    assert (last["kind"], last["content"]) == ("error", "The model timed out")
    assert last["thread_id"] == "t-1"


def test_a_second_failure_leaves_the_claim_for_a_handler(client):
    start(client, "CLM-1004")
    fail(client, "CLM-1004")
    start(client, "CLM-1004")
    claim = fail(client, "CLM-1004", "The agent went round in circles").json()
    assert (claim["status"], claim["attempts"]) == ("left_for_handler", 2)
    assert start(client, "CLM-1004").status_code == 409
    assert decide(client, "CLM-1004", "decline", 0).status_code == 409
    queue = {c["claim_id"]: c for c in client.get("/api/claims").json()}
    assert queue["CLM-1004"]["status"] == "left_for_handler"
    errors = [
        s["content"]
        for s in client.get("/api/claims/CLM-1004/steps").json()
        if s["kind"] == "error"
    ]
    assert errors == ["The model timed out", "The agent went round in circles"]


def test_failure_needs_a_claim_in_progress(client):
    assert fail(client, "CLM-1001").status_code == 409
    start(client, "CLM-1001")
    decide(client, "CLM-1001", "approve", 420.0)
    assert fail(client, "CLM-1001").status_code == 409
    start(client, "CLM-1002")
    decide(client, "CLM-1002", "approve", 1350.0)
    assert fail(client, "CLM-1002").status_code == 409
    assert client.get("/api/claims/CLM-1002").json()["status"] == (
        "waiting_for_sign_off"
    )
    assert client.get("/api/claims/CLM-1001/steps").json() == []
    assert fail(client, "CLM-9999").status_code == 404


def test_failure_needs_a_reason(client):
    start(client, "CLM-1001")
    assert fail(client, "CLM-1001", "").status_code == 422
    assert client.get("/api/claims/CLM-1001").json()["status"] == "in_progress"


def start_run(client, cap=5):
    return client.post("/api/runs", json={"cap": cap})


def write(client, run_id, *todos):
    return client.put(
        f"/api/runs/{run_id}/todos",
        json={"todos": [{"content": c, "status": s} for c, s in todos]},
    )


def test_no_run_yet(client):
    response = client.get("/api/runs/latest")
    assert response.status_code == 200
    assert response.json() is None


def test_start_a_run(client):
    run = start_run(client).json()
    assert run["cap"] == 5
    assert run["status"] == "running"
    assert run["started_at"]
    assert (run["finished_at"], run["summary"], run["todos"]) == (None, None, [])
    assert client.get("/api/runs/latest").json() == run


@pytest.mark.parametrize("cap", [0, -1])
def test_a_run_needs_a_cap(client, cap):
    assert start_run(client, cap).status_code == 422


def test_write_todos_replaces_the_list(client):
    run_id = start_run(client).json()["run_id"]
    write(client, run_id, ("CLM-1001", "to_do"), ("CLM-1002", "to_do"))
    run = write(
        client,
        run_id,
        ("CLM-1001", "done"),
        ("CLM-1002", "in_progress"),
        ("Write the summary", "to_do"),
    ).json()
    assert run["todos"] == [
        {"content": "CLM-1001", "status": "done"},
        {"content": "CLM-1002", "status": "in_progress"},
        {"content": "Write the summary", "status": "to_do"},
    ]
    assert client.get("/api/runs/latest").json()["todos"] == run["todos"]


def test_invalid_todos(client):
    run_id = start_run(client).json()["run_id"]
    assert write(client, run_id, ("CLM-1001", "blocked")).status_code == 422
    assert write(client, run_id, ("", "to_do")).status_code == 422
    assert write(client, "RUN-9", ("CLM-1001", "to_do")).status_code == 404


def test_finish_a_run(client):
    run_id = start_run(client).json()["run_id"]
    write(client, run_id, ("CLM-1001", "done"))
    finish = client.post(
        f"/api/runs/{run_id}/finish", json={"summary": "Worked 1 claim."}
    )
    run = finish.json()
    assert (run["status"], run["summary"]) == ("finished", "Worked 1 claim.")
    assert run["finished_at"]
    assert run["todos"] == [{"content": "CLM-1001", "status": "done"}]
    assert write(client, run_id, ("CLM-1001", "to_do")).status_code == 409
    again = client.post(f"/api/runs/{run_id}/finish", json={"summary": "Again."})
    assert again.status_code == 409

    newer = start_run(client, 2).json()
    assert client.get("/api/runs/latest").json()["run_id"] == newer["run_id"]


def test_finish_needs_a_summary_and_a_known_run(client):
    run_id = start_run(client).json()["run_id"]
    empty = client.post(f"/api/runs/{run_id}/finish", json={"summary": ""})
    assert empty.status_code == 422
    unknown = client.post("/api/runs/RUN-9/finish", json={"summary": "Done."})
    assert unknown.status_code == 404
    assert unknown.json()["detail"] == "Run RUN-9 not found"
