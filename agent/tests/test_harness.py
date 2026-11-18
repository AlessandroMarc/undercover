import itertools

import pytest
from langchain_core.messages import AIMessage

from agent import harness, main
from agent.main import ClaimError
from agent.tests.stubs import StubModel, calls, decision, stub


@pytest.fixture(autouse=True)
def no_retry_delay(monkeypatch):
    monkeypatch.setattr(main, "RETRY_DELAY", 0)


def broken(times=3):
    return [TimeoutError("provider timed out")] * times


def test_a_transient_error_is_retried(api):
    llm = stub(
        TimeoutError("slow"),
        calls(decision("CLM-1001", "decline", 0.0)),
        AIMessage(content="Declined."),
    )
    assert harness.work_claim("CLM-1001", llm) == "CLM-1001: decline"
    assert api.get("/api/claims/CLM-1001").json()["status"] == "decided"


def test_a_claim_that_keeps_failing_goes_back_then_to_a_handler(api):
    first = harness.work_claim("CLM-1001", stub(*broken()))
    assert first == (
        "CLM-1001: failed (TimeoutError: provider timed out), back in the queue"
    )
    claim = api.get("/api/claims/CLM-1001").json()
    assert claim["status"] == "waiting"
    steps = api.get("/api/claims/CLM-1001/steps").json()
    assert "Attempt 1 failed: TimeoutError" in steps[-1]["text"]

    second = harness.work_claim("CLM-1001", stub(*broken()))
    assert second.startswith("CLM-1001: failed twice")
    assert api.get("/api/claims/CLM-1001").json()["status"] == "needs_handler"


def test_a_claim_with_no_decision_fails(api):
    line = harness.work_claim("CLM-1001", stub(AIMessage(content="I am done.")))
    assert "the agent finished without a decision" in line
    assert api.get("/api/claims/CLM-1001").json()["status"] == "waiting"


def test_an_agent_that_loops_hits_the_call_limit(api, monkeypatch):
    monkeypatch.setattr(main, "CALL_LIMIT", 3)
    forever = StubModel(
        messages=itertools.repeat(calls(("get_plan", {"plan": "premium"})))
    )
    line = harness.work_claim("CLM-1001", forever)
    assert "ModelCallLimitExceededError" in line
    assert api.get("/api/claims/CLM-1001").json()["status"] == "waiting"


def test_a_claim_decided_before_the_failure_is_paid_once_and_not_run_again(api):
    llm = stub(calls(decision("CLM-1001", "approve", 420.0)), *broken())
    assert harness.work_claim("CLM-1001", llm) == "CLM-1001: approve, payout $420.00"
    claim = api.get("/api/claims/CLM-1001").json()
    assert claim["status"] == "decided"
    assert claim["payment"]["amount"] == 420.0
    with pytest.raises(ClaimError, match="already decided"):
        harness.work_claim("CLM-1001", stub())
    assert api.get("/api/claims/CLM-1001").json()["payment"]["amount"] == 420.0


def test_a_payout_over_the_limit_is_left_for_sign_off(api):
    llm = stub(calls(decision("CLM-1002", "approve", 1250.0)), *broken())
    line = harness.work_claim("CLM-1002", llm)
    assert line == "CLM-1002: approve, payout $1,250.00, waiting for sign-off"
    claim = api.get("/api/claims/CLM-1002").json()
    assert claim["status"] == "awaiting_signoff"
    assert claim["payment"] is None


def test_an_unknown_claim_is_an_error_not_a_failure(api):
    with pytest.raises(ClaimError, match="CLM-0000 not found"):
        harness.work_claim("CLM-0000", stub())
