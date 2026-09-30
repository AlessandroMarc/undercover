import logging
import sqlite3
from contextlib import closing
from functools import partial

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver

from agent import __main__ as cli
from agent import api, harness
from agent.tests.stub_model import call, decide, pay, stub
from agent.tools import RunContext


def leave_waiting(database, *claim_ids):
    """Leave every claim but the ones named for a handler, out of the agent's way."""
    with closing(sqlite3.connect(database)) as db, db:
        db.execute("UPDATE claims SET status = 'left_for_handler'")
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


def test_a_whole_run(client, database, caplog):
    caplog.set_level(logging.INFO, logger="agent")
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
        *decide("approve", 420.0, pay(420.0)),
        *decide("refer", 0),
        *decide("decline", 0),
    )
    harness.run_queue(None, queue_model, claim_model)

    assert {claims(client)[i]["status"] for i in ids} == {"decided"}
    run = latest(client)
    assert (run["status"], run["cap"], run["summary"]) == ("finished", 3, summary)
    assert run["todos"] == [{"content": i, "status": "done"} for i in ids]

    system, first = queue_model.prompts[0]
    assert isinstance(system, SystemMessage)
    assert system.content == client.get("/api/instructions").json()["queue"]
    assert isinstance(first, HumanMessage)
    assert first.content == "Please work the queue. This run can work up to 3 claims."
    assert caplog.messages == [
        "CLM-1001  approve  $420.00",
        "CLM-1002  refer  $0.00",
        "CLM-1003  decline  $0.00",
        summary,
    ]


def test_the_cap(client, database):
    leave_waiting(database, "CLM-1001", "CLM-1002", "CLM-1003", "CLM-1004")
    queue_model = stub(work("CLM-1001"), work("CLM-1002"), work("CLM-1003"), done())
    claim_model = stub(*decide("refer", 0), *decide("refer", 0))
    harness.run_queue(2, queue_model, claim_model)

    refusal = tool_replies(queue_model)[-1]
    assert refusal == (
        "Refused: this run can work 2 claims, and has started CLM-1001, CLM-1002"
    )
    after = claims(client)
    assert [after[i]["status"] for i in ("CLM-1001", "CLM-1002")] == ["decided"] * 2
    for claim_id in ("CLM-1003", "CLM-1004"):
        claim = client.get(f"/api/claims/{claim_id}").json()
        assert (claim["status"], claim["attempts"]) == ("waiting", 0)
    assert latest(client)["cap"] == 2


def test_the_cap_holds_when_claims_are_handed_over_together(client, database):
    leave_waiting(database, "CLM-1001", "CLM-1002", "CLM-1003")
    together = [work(i).tool_calls[0] for i in ("CLM-1001", "CLM-1002", "CLM-1003")]
    queue_model = stub(AIMessage(content="", tool_calls=together), done())
    claim_model = stub(*decide("refer", 0), *decide("refer", 0), *decide("refer", 0))
    harness.run_queue(2, queue_model, claim_model)

    replies = tool_replies(queue_model)
    assert sorted(replies)[-1].startswith("Refused: this run can work 2 claims")
    assert [c["status"] for c in claims(client).values()].count("decided") == 2


def test_a_claim_that_cant_be_started_leaves_the_cap_alone(client, database):
    leave_waiting(database, "CLM-1001")
    queue_model = stub(work("CLM-1003"), work("CLM-1001"), done())
    harness.run_queue(1, queue_model, stub(*decide("refer", 0)))

    assert tool_replies(queue_model) == [
        "Refused with status 409: Claim CLM-1003 is not waiting",
        "CLM-1001  refer  $0.00",
    ]
    assert client.get("/api/claims/CLM-1003").json()["attempts"] == 0


def test_each_claim_in_a_run_starts_clean_and_leaves_nothing_behind(database):
    leave_waiting(database, "CLM-1001", "CLM-1003")
    claim_model = stub(*decide("decline", 0), *decide("refer", 0))
    work_claim = partial(harness.work_claim, agent=harness.claim_agent(claim_model))
    run = RunContext(api.start_run(2)["run_id"], 2, work_claim)
    queue_agent = harness.queue_agent(
        stub(work("CLM-1001"), work("CLM-1003"), done()), 2
    )
    harness.work_queue(run, queue_agent)

    firsts = [prompt for prompt in claim_model.prompts if len(prompt) == 2]
    assert [prompt[1].content for prompt in firsts] == [
        "Claim CLM-1001",
        "Claim CLM-1003",
    ]
    saver = queue_agent.checkpointer
    assert isinstance(saver, InMemorySaver)
    kept = [c.config.get("configurable", {}) for c in saver.list(None)]
    assert {config["checkpoint_ns"] for config in kept} == {""}


def test_a_cap_above_the_queue_is_the_queue(client, database):
    leave_waiting(database, "CLM-1001")
    claim_model = stub(*decide("refer", 0))
    harness.run_queue(5, stub(work("CLM-1001"), done()), claim_model)
    assert latest(client)["cap"] == 1


def test_a_failed_claim_does_not_stop_the_run_and_is_tried_again(client, database):
    leave_waiting(database, "CLM-1001", "CLM-1002", "CLM-1003")
    queue_model = stub(
        work("CLM-1001"), work("CLM-1002"), work("CLM-1003"), work("CLM-1001"), done()
    )
    claim_model = stub(
        RuntimeError("503: The model is unavailable"),
        *decide("refer", 0),
        *decide("decline", 0),
        *decide("decline", 0),
    )
    harness.run_queue(None, queue_model, claim_model)

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
        *decide("refer", 0),
        RuntimeError("Timed out again"),
    )
    harness.run_queue(None, queue_model, claim_model)

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
        *decide("refer", 0),
        *decide("refer", 0),
    )
    harness.run_queue(None, queue_model, claim_model)

    assert asked(queue_model)[1] == (
        "These claims are still waiting within the run's cap: CLM-1001. "
        "Please work them, then finish with the summary."
    )
    assert claims(client)["CLM-1001"]["status"] == "decided"
    assert latest(client)["summary"] == "Worked both claims."


def test_the_harness_names_the_oldest_claims_first(client, database):
    leave_waiting(database, "CLM-1002", "CLM-1008")
    queue_model = stub(done(), done(), done())
    harness.run_queue(1, queue_model, stub())
    assert asked(queue_model)[1].startswith(
        "These claims are still waiting within the run's cap: CLM-1008."
    )


def test_the_harness_reminds_twice_at_most(client, database):
    leave_waiting(database, "CLM-1001", "CLM-1002")
    queue_model = stub(done("Done."), done("Still done."), done("Done for good."))
    harness.run_queue(1, queue_model, stub())

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
    harness.run_queue(None, stub(work("CLM-1001"), done()), stub(*decide("refer", 0)))

    steps = client.get("/api/claims/CLM-1001/steps").json()
    assert (steps[0]["kind"], steps[0]["content"]) == ("error", harness.STOPPED)
    claim = client.get("/api/claims/CLM-1001").json()
    assert (claim["status"], claim["attempts"]) == ("decided", 2)


def test_a_failure_of_the_queue_agent_finishes_the_run(client, database):
    leave_waiting(database, "CLM-1001")
    queue_model = stub(work("CLM-1001"), RuntimeError("The provider is down"))
    with pytest.raises(RuntimeError, match="The provider is down"):
        harness.run_queue(None, queue_model, stub(*decide("refer", 0)))

    run = latest(client)
    assert run["status"] == "finished"
    assert run["summary"] == "The run stopped: RuntimeError: The provider is down"
    assert "in_progress" not in {c["status"] for c in claims(client).values()}


def test_nothing_waiting(client, database, caplog):
    caplog.set_level(logging.INFO, logger="agent")
    leave_waiting(database)
    harness.run_queue(None, stub(), stub())
    assert caplog.messages == ["No claims are waiting"]
    assert latest(client) is None


def test_an_empty_summary_is_filled_in(client, database):
    leave_waiting(database, "CLM-1001")
    harness.run_queue(None, stub(work("CLM-1001"), done("")), stub(*decide("refer", 0)))
    assert latest(client)["summary"] == harness.NO_SUMMARY


def test_command_line_works_the_queue(monkeypatch):
    runs = []
    monkeypatch.setattr(cli, "model", lambda: "model")
    monkeypatch.setattr(cli, "run_queue", lambda *args: runs.append(args))
    cli.main([])
    cli.main(["--cap", "5"])
    assert runs == [(None, "model", "model"), (5, "model", "model")]
    for args in (["--cap", "0"], ["--cap", "five"], ["CLM-1001", "--cap", "5"]):
        with pytest.raises(SystemExit):
            cli.main(args)
