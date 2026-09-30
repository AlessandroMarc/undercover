import pytest


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
