import sqlite3
from contextlib import closing

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from agent import __main__ as cli
from agent import queue
from agent.tests.test_agent import call, decide, pay, stub


def leave_waiting(database, *claim_ids):
    """Decide every claim except the ones named, which stay waiting."""
    with closing(sqlite3.connect(database)) as db, db:
        db.execute("UPDATE claims SET status = 'decided'")
        db.executemany(
            "UPDATE claims SET status = 'waiting' WHERE claim_id = ?",
            [(claim_id,) for claim_id in claim_ids],
        )


def todos(*items):
    return call("write_todos", todos=[{"content": c, "status": s} for c, s in items])


def work(claim_id):
    return call("work_claim", claim_id=claim_id)


def done(text="Worked the claims."):
    return AIMessage(content=text)


def claims(client):
    return {c["claim_id"]: c for c in client.get("/api/claims").json()}


def latest(client):
    return client.get("/api/runs/latest").json()


def tool_replies(model):
    """The replies to the queue agent's tool calls, in the order it saw them."""
    return [m.text for m in model.prompts[-1] if isinstance(m, ToolMessage)]


def asked(model):
    """What the queue agent was asked: the first message, then any reminders."""
    return [m.text for m in model.prompts[-1] if isinstance(m, HumanMessage)]


def test_queue_tools_are_named_after_backend_operations(client):
    operations = {
        operation["operationId"]
        for path in client.get("/openapi.json").json()["paths"].values()
        for operation in path.values()
    }
    names = [t.name for t in queue.queue_tools("run-1", 3, set(), None)]
    assert names == ["list_claims", "write_todos", "work_claim"]
    assert {"list_claims", "write_todos"} <= operations


def test_a_whole_run(client, database, capsys):
    leave_waiting(database, "CLM-1001", "CLM-1002", "CLM-1003")
    ids = ["CLM-1001", "CLM-1002", "CLM-1003"]
    summary = "Worked 3 claims: 1 approved, 1 referred and 1 declined."
    queue_model = stub(
        call("list_claims"),
        todos(*((i, "to_do") for i in ids)),
        todos((ids[0], "in_progress"), (ids[1], "to_do"), (ids[2], "to_do")),
        work(ids[0]),
        todos((ids[0], "done"), (ids[1], "in_progress"), (ids[2], "to_do")),
        work(ids[1]),
        todos((ids[0], "done"), (ids[1], "done"), (ids[2], "in_progress")),
        work(ids[2]),
        todos(*((i, "done") for i in ids)),
        done(summary),
    )
    claim_model = stub(
        *decide("CLM-1001", "approve", 420.0, pay("CLM-1001", 420.0)),
        *decide("CLM-1002", "refer", 0),
        *decide("CLM-1003", "decline", 0),
    )
    queue.run_queue(None, queue_model, claim_model)

    assert {claims(client)[i]["status"] for i in ids} == {"decided"}
    run = latest(client)
    assert (run["status"], run["cap"], run["summary"]) == ("finished", 3, summary)
    assert run["todos"] == [{"content": i, "status": "done"} for i in ids]

    system, first = queue_model.prompts[0]
    assert isinstance(system, SystemMessage)
    assert system.content == client.get("/api/instructions").json()["queue"]
    assert isinstance(first, HumanMessage)
    assert first.content == "Please work the queue. This run can work up to 3 claims."
    assert capsys.readouterr().out.splitlines() == [
        "CLM-1001  approve  $420.00",
        "CLM-1002  refer  $0.00",
        "CLM-1003  decline  $0.00",
        summary,
    ]


def test_the_cap(client, database):
    leave_waiting(database, "CLM-1001", "CLM-1002", "CLM-1003", "CLM-1004")
    queue_model = stub(work("CLM-1001"), work("CLM-1002"), work("CLM-1003"), done())
    claim_model = stub(*decide("CLM-1001", "refer", 0), *decide("CLM-1002", "refer", 0))
    queue.run_queue(2, queue_model, claim_model)

    refusal = tool_replies(queue_model)[-1]
    assert refusal == (
        "Refused: this run can work 2 claims, and it has started CLM-1001, CLM-1002"
    )
    after = claims(client)
    assert [after[i]["status"] for i in ("CLM-1001", "CLM-1002")] == ["decided"] * 2
    for claim_id in ("CLM-1003", "CLM-1004"):
        claim = client.get(f"/api/claims/{claim_id}").json()
        assert (claim["status"], claim["attempts"]) == ("waiting", 0)
    assert latest(client)["cap"] == 2


def test_a_cap_above_the_queue_is_the_queue(client, database):
    leave_waiting(database, "CLM-1001")
    claim_model = stub(*decide("CLM-1001", "refer", 0))
    queue.run_queue(5, stub(work("CLM-1001"), done()), claim_model)
    assert latest(client)["cap"] == 1


def test_a_failed_claim_does_not_stop_the_run_and_is_tried_again(client, database):
    leave_waiting(database, "CLM-1001", "CLM-1002", "CLM-1003")
    queue_model = stub(
        work("CLM-1001"), work("CLM-1002"), work("CLM-1003"), work("CLM-1001"), done()
    )
    claim_model = stub(
        RuntimeError("503: The model is unavailable"),
        *decide("CLM-1002", "refer", 0),
        *decide("CLM-1003", "decline", 0),
        *decide("CLM-1001", "decline", 0),
    )
    queue.run_queue(None, queue_model, claim_model)

    assert tool_replies(queue_model) == [
        "CLM-1001  failed: RuntimeError: 503: The model is unavailable,"
        " back in the queue",
        "CLM-1002  refer  $0.00",
        "CLM-1003  decline  $0.00",
        "CLM-1001  decline  $0.00",
    ]
    first = client.get("/api/claims/CLM-1001").json()
    assert (first["status"], first["attempts"]) == ("decided", 2)
    steps = client.get("/api/claims/CLM-1001/steps").json()
    assert steps[0]["kind"] == "error"
    assert len({s["thread_id"] for s in steps}) == 2
    assert steps[1]["thread_id"] != steps[0]["thread_id"]
    assert latest(client)["status"] == "finished"


def test_a_claim_that_fails_twice_is_left_for_a_handler(client, database):
    leave_waiting(database, "CLM-1001", "CLM-1002")
    queue_model = stub(work("CLM-1001"), work("CLM-1002"), work("CLM-1001"), done())
    claim_model = stub(
        RuntimeError("Timed out"),
        *decide("CLM-1002", "refer", 0),
        RuntimeError("Timed out again"),
    )
    queue.run_queue(None, queue_model, claim_model)

    assert tool_replies(queue_model)[-1] == (
        "CLM-1001  failed: RuntimeError: Timed out again, left for a handler"
    )
    after = claims(client)
    assert after["CLM-1001"]["status"] == "left_for_handler"
    assert after["CLM-1002"]["status"] == "decided"
    assert latest(client)["status"] == "finished"


def test_the_harness_names_missed_claims(client, database):
    leave_waiting(database, "CLM-1001", "CLM-1002")
    queue_model = stub(
        work("CLM-1001"),
        work("CLM-1002"),
        done("Finished early."),
        work("CLM-1001"),
        done("Worked both claims."),
    )
    claim_model = stub(
        RuntimeError("Timed out"),
        *decide("CLM-1002", "refer", 0),
        *decide("CLM-1001", "refer", 0),
    )
    queue.run_queue(None, queue_model, claim_model)

    assert asked(queue_model)[1] == (
        "These claims are still waiting within the run's cap: CLM-1001. "
        "Please work them, then finish with the summary."
    )
    assert claims(client)["CLM-1001"]["status"] == "decided"
    assert latest(client)["summary"] == "Worked both claims."


def test_the_harness_reminds_twice_at_most(client, database):
    leave_waiting(database, "CLM-1001", "CLM-1002")
    queue_model = stub(done("Done."), done("Still done."), done("Done for good."))
    queue.run_queue(1, queue_model, stub())

    first, reminder, again = asked(queue_model)
    assert reminder == again
    assert reminder.startswith(
        "These claims are still waiting within the run's cap: CLM-1001."
    )
    run = latest(client)
    assert (run["status"], run["summary"]) == ("finished", "Done for good.")
    assert claims(client)["CLM-1001"]["status"] == "waiting"


def test_a_claim_left_in_progress_is_put_back(client, database):
    leave_waiting(database, "CLM-1001")
    client.post("/api/claims/CLM-1001/start", json={"thread_id": "crashed"})
    queue.run_queue(
        None, stub(work("CLM-1001"), done()), stub(*decide("CLM-1001", "refer", 0))
    )

    steps = client.get("/api/claims/CLM-1001/steps").json()
    assert (steps[0]["kind"], steps[0]["content"]) == ("error", queue.STOPPED)
    claim = client.get("/api/claims/CLM-1001").json()
    assert (claim["status"], claim["attempts"]) == ("decided", 2)


def test_a_failure_of_the_queue_agent_finishes_the_run(client, database):
    leave_waiting(database, "CLM-1001")
    queue_model = stub(work("CLM-1001"), RuntimeError("The provider is down"))
    with pytest.raises(RuntimeError, match="The provider is down"):
        queue.run_queue(None, queue_model, stub(*decide("CLM-1001", "refer", 0)))

    run = latest(client)
    assert run["status"] == "finished"
    assert run["summary"] == "The run stopped: RuntimeError: The provider is down"
    assert "in_progress" not in {c["status"] for c in claims(client).values()}


def test_nothing_waiting(client, database, capsys):
    leave_waiting(database)
    queue.run_queue(None, stub(), stub())
    assert capsys.readouterr().out == "No claims are waiting\n"
    assert latest(client) is None


def test_an_empty_summary_is_filled_in(client, database):
    leave_waiting(database, "CLM-1001")
    queue.run_queue(
        None, stub(work("CLM-1001"), done("")), stub(*decide("CLM-1001", "refer", 0))
    )
    assert latest(client)["summary"] == "The run finished without a summary."


def test_command_line(monkeypatch, capsys):
    runs = []
    monkeypatch.setattr(cli, "run_queue", runs.append)
    monkeypatch.setattr(cli, "work_claim", lambda claim_id: f"{claim_id}  refer  $0.00")
    cli.main([])
    cli.main(["--cap", "5"])
    cli.main(["CLM-1001"])
    assert runs == [None, 5]
    assert capsys.readouterr().out == "CLM-1001  refer  $0.00\n"
    for cap in ("0", "five"):
        with pytest.raises(SystemExit):
            cli.main(["--cap", cap])
