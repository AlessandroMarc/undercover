from backend.tests.test_workflow import CLAIM, decide, pay, status


def start(client, claim_id=CLAIM):
    return client.post(f"/api/claims/{claim_id}/start")


def fail(client, reason="timeout", claim_id=CLAIM):
    return client.post(f"/api/claims/{claim_id}/failure", json={"reason": reason})


def test_a_claim_that_fails_twice_is_left_for_a_handler(client):
    start(client)
    first = fail(client).json()
    assert first["status"] == "waiting"
    start(client)
    assert fail(client, "bad reply").json()["status"] == "needs_handler"
    assert start(client).status_code == 409
    steps = client.get(f"/api/claims/{CLAIM}/steps").json()
    assert [step["text"] for step in steps] == [
        "Attempt 1 failed: timeout. Back in the queue.",
        "Attempt 2 failed: bad reply. Left for a handler.",
    ]
    others = {
        c["status"] for c in client.get("/api/claims").json() if c["claim_id"] != CLAIM
    }
    assert others == {"waiting"}


def test_only_a_claim_in_progress_can_fail(client):
    assert fail(client).status_code == 409
    assert fail(client, claim_id="CLM-0000").status_code == 404
    start(client)
    decide(client)
    assert fail(client).status_code == 409
    assert status(client) == "decided"


def test_a_failed_claim_keeps_its_decision_and_cannot_be_paid_twice(client):
    start(client)
    decide(client)
    assert decide(client).status_code == 409
    assert pay(client, 420.0).status_code == 200
    assert pay(client, 420.0).status_code == 409
    assert start(client).status_code == 409


def test_the_latest_run_and_its_todo_list(client):
    assert client.get("/api/runs/latest").json() is None
    run = client.post("/api/runs", json={"cap": 5}).json()
    assert run["cap"] == 5
    assert run["status"] == "running"
    assert run["todos"] == []
    path = f"/api/runs/{run['run_id']}/todos"
    two = [
        {"content": "CLM-1001 trip delay", "status": "in_progress"},
        {"content": "CLM-1002 baggage", "status": "todo"},
    ]
    assert client.put(path, json={"todos": two}).json()["todos"] == two
    one = client.put(path, json={"todos": two[:1]}).json()
    assert one["todos"] == two[:1]
    assert client.get("/api/runs/latest").json()["todos"] == two[:1]
    bad = {"content": "x", "status": "maybe"}
    assert client.put(path, json={"todos": [bad]}).status_code == 422
    assert client.put("/api/runs/99/todos", json={"todos": []}).status_code == 404


def test_a_run_finishes_once(client):
    run_id = client.post("/api/runs", json={"cap": 1}).json()["run_id"]
    path = f"/api/runs/{run_id}/finish"
    done = client.post(path, json={"status": "finished", "summary": "All done."})
    assert done.json()["status"] == "finished"
    assert done.json()["summary"] == "All done."
    assert done.json()["finished_at"]
    assert (
        client.post(path, json={"status": "failed", "summary": "x"}).status_code == 409
    )
    todos = client.put(f"/api/runs/{run_id}/todos", json={"todos": []})
    assert todos.status_code == 409


def test_read_steps_are_listed_in_order(client):
    for kind in ("tool_call", "read"):
        client.post(f"/api/claims/{CLAIM}/steps", json={"kind": kind, "text": kind})
    steps = client.get(f"/api/claims/{CLAIM}/steps").json()
    assert [step["kind"] for step in steps] == ["tool_call", "read"]
