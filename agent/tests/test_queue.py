import pytest
from langchain_core.messages import AIMessage

from agent import main, queue_agent, work
from agent.queue_agent import QueueRun, RunFailed, queue_tools, run_queue
from agent.tests.stubs import calls, decision, stub


@pytest.fixture(autouse=True)
def no_retry_delay(monkeypatch):
    monkeypatch.setattr(main, "RETRY_DELAY", 0)


def todos(*items):
    return ("write_todos", {"todos": [{"content": c, "status": s} for c, s in items]})


def take(claim_id):
    return calls(("work_claim", {"claim_id": claim_id}))


def declined(claim_id):
    """The scripted replies of a claim agent that declines the claim."""
    return [calls(decision(claim_id, "decline", 0.0)), AIMessage(content="Declined.")]


def finish(summary="All done."):
    return calls(("finish_run", {"summary": summary}))


def status(api, claim_id):
    return api.get(f"/api/claims/{claim_id}").json()["status"]


def statuses(api):
    return [claim["status"] for claim in api.get("/api/claims").json()]


def test_the_run_keeps_a_todo_list_and_a_summary(api):
    llm = stub(
        calls(("list_waiting_claims", {})),
        calls(todos(("CLM-1001 trip delay", "todo"))),
        calls(todos(("CLM-1001 trip delay", "in_progress"))),
        take("CLM-1001"),
        *declined("CLM-1001"),
        calls(todos(("CLM-1001 trip delay", "done"))),
        finish("One claim declined."),
        AIMessage(content="Finished."),
    )
    assert run_queue(1, "thread", llm) == "One claim declined."
    run = api.get("/api/runs/latest").json()
    assert run["status"] == "finished"
    assert run["cap"] == 1
    assert run["todos"] == [{"content": "CLM-1001 trip delay", "status": "done"}]
    assert status(api, "CLM-1001") == "decided"
    assert statuses(api).count("waiting") == 24


def test_the_cap_stops_a_third_claim(api, capsys):
    llm = stub(
        take("CLM-1001"),
        *declined("CLM-1001"),
        take("CLM-1002"),
        *declined("CLM-1002"),
        take("CLM-1003"),
        finish(),
        AIMessage(content="Finished."),
    )
    run_queue(2, "thread", llm)
    assert "Error: your cap of 2 claims is used up" in capsys.readouterr().out
    assert status(api, "CLM-1003") == "waiting"
    assert statuses(api).count("waiting") == 23


def test_a_failed_claim_goes_back_and_is_tried_again(api, capsys):
    llm = stub(
        take("CLM-1001"),
        *[TimeoutError("slow")] * 3,
        finish(),
        take("CLM-1001"),
        *declined("CLM-1001"),
        take("CLM-1002"),
        *declined("CLM-1002"),
        finish(),
        AIMessage(content="Finished."),
    )
    run_queue(2, "thread", llm)
    out = capsys.readouterr().out
    assert "back in the queue" in out
    assert "Not finished. CLM-1001 still waiting" in out
    assert status(api, "CLM-1001") == "decided"
    assert status(api, "CLM-1002") == "decided"
    assert api.get("/api/runs/latest").json()["status"] == "finished"


def test_a_claim_that_fails_twice_is_left_for_a_handler_and_the_run_goes_on(api):
    llm = stub(
        take("CLM-1001"),
        *[TimeoutError("slow")] * 3,
        take("CLM-1001"),
        *[TimeoutError("slow")] * 3,
        take("CLM-1002"),
        *declined("CLM-1002"),
        calls(todos(("CLM-1001", "left_for_handler"), ("CLM-1002", "done"))),
        finish(),
        AIMessage(content="Finished."),
    )
    run_queue(2, "thread", llm)
    assert status(api, "CLM-1001") == "needs_handler"
    assert status(api, "CLM-1002") == "decided"
    run = api.get("/api/runs/latest").json()
    assert run["status"] == "finished"
    assert run["todos"][0]["status"] == "left_for_handler"


def test_finishing_is_refused_while_the_cap_is_unused(api, capsys):
    llm = stub(
        take("CLM-1001"),
        *declined("CLM-1001"),
        finish(),
        take("CLM-1002"),
        *declined("CLM-1002"),
        finish(),
        AIMessage(content="Finished."),
    )
    run_queue(2, "thread", llm)
    assert "You have taken 1 of your 2 claims" in capsys.readouterr().out
    assert status(api, "CLM-1002") == "decided"


def test_with_no_limit_the_cap_is_every_waiting_claim(api):
    with pytest.raises(RunFailed, match="before it finished"):
        run_queue(None, "thread", stub(AIMessage(content="Nothing to do.")))
    run = api.get("/api/runs/latest").json()
    assert run["cap"] == 25
    assert run["status"] == "failed"
    assert "before it finished" in run["summary"]


def test_a_run_that_breaks_leaves_no_claim_in_progress(api, monkeypatch):
    def break_after_starting(claim_id, llm):
        api.post(f"/api/claims/{claim_id}/start")
        raise RuntimeError("boom")

    monkeypatch.setattr(queue_agent, "work_claim", break_after_starting)
    with pytest.raises(RunFailed, match="RuntimeError: boom"):
        run_queue(1, "thread", stub(take("CLM-1001")))
    assert status(api, "CLM-1001") == "waiting"
    assert api.get("/api/runs/latest").json()["status"] == "failed"


def test_the_queue_tools_check_what_they_are_given(api):
    run_id = api.post("/api/runs", json={"cap": 1}).json()["run_id"]
    tools = {t.name: t for t in queue_tools(QueueRun(run_id, 1, stub()))}
    listing = tools["list_waiting_claims"].invoke({})
    assert listing.startswith("CLM-1001 | trip_delay | $420.00 | ")
    assert len(listing.splitlines()) == 25
    assert tools["work_claim"].invoke({"claim_id": "CLM-0000"}).startswith("Error")
    api.post("/api/claims/CLM-1001/start")
    assert "not waiting" in tools["work_claim"].invoke({"claim_id": "CLM-1001"})


def test_the_queue_agent_cannot_decide_or_pay(api):
    run_id = api.post("/api/runs", json={"cap": 1}).json()["run_id"]
    names = {t.name for t in queue_tools(QueueRun(run_id, 1, stub()))}
    assert names == {"list_waiting_claims", "work_claim", "write_todos", "finish_run"}


def test_work_runs_the_given_claims(api, capsys):
    llm = stub(*declined("CLM-1001"), *declined("CLM-1002"))
    work.main(["CLM-1001", "CLM-1002"], llm)
    assert "CLM-1002: decline" in capsys.readouterr().out
    assert status(api, "CLM-1001") == "decided"
    assert api.get("/api/runs/latest").json() is None


def test_work_runs_the_queue_with_a_limit(api, capsys):
    llm = stub(
        take("CLM-1001"), *declined("CLM-1001"), finish("Done."), AIMessage(content=".")
    )
    work.main(["--limit", "1"], llm)
    assert capsys.readouterr().out.strip().endswith("Done.")


def test_work_stops_on_an_unknown_claim():
    with pytest.raises(SystemExit, match="CLM-0000: CLM-0000 not found"):
        work.main(["CLM-0000"], stub())


def test_work_stops_when_the_run_fails(api):
    with pytest.raises(SystemExit, match="before it finished"):
        work.main([], stub(AIMessage(content="Nothing.")))


@pytest.mark.parametrize(
    "argv", [["--limit", "0"], ["--limit", "-2"], ["CLM-1001", "--limit", "2"]]
)
def test_work_refuses_a_bad_limit(argv):
    with pytest.raises(SystemExit) as stop:
        work.main(argv, stub())
    assert stop.value.code == 2
