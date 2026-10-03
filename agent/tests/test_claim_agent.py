import itertools
import json
import logging

import pytest
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage

from agent import __main__ as cli
from agent import api, harness
from agent.tests.stub_model import StubModel, call, decide, pay, record, stub


def work(claim_id, model):
    return harness.work_claim(claim_id, harness.claim_agent(model))


def steps_of(client, claim_id):
    return client.get(f"/api/claims/{claim_id}/steps").json()


def test_approves_and_pays_within_the_limit(client, caplog):
    caplog.set_level(logging.INFO, logger="agent")
    model = stub(
        call("get_claim"),
        call("get_policy", policy_id="POL-2001"),
        call("get_claim_history", customer_id="CUS-3001"),
        record("approve", 420.0),
        pay(420.0, "Paying now."),
        AIMessage(content="Decision: approve."),
    )
    assert work("CLM-1001", model) == "CLM-1001  approve  $420.00"
    assert caplog.messages == ["CLM-1001  approve  $420.00"]

    claim = client.get("/api/claims/CLM-1001").json()
    assert claim["status"] == "decided"
    assert claim["attempts"] == 1
    assert claim["decision"]["payout"] == 420.0
    assert claim["payment"]["amount"] == 420.0
    assert len(claim["thread_id"]) == 36

    steps = steps_of(client, "CLM-1001")
    assert [s["kind"] for s in steps] == [
        *(["tool_call", "tool_result"] * 4),
        "message",
        "tool_call",
        "tool_result",
        "message",
    ]
    assert steps[0]["content"] == "get_claim()"
    assert steps[1]["content"].startswith('get_claim: {"claim_id": "CLM-1001"')
    assert steps[8]["content"] == "Paying now."
    assert steps[9]["content"] == "pay_claim(amount=420.0)"
    assert steps[-1]["content"] == "Decision: approve."
    assert {s["thread_id"] for s in steps} == {claim["thread_id"]}


def test_uses_the_claim_instructions_from_the_backend(client):
    model = stub(*decide("refer", 0))
    work("CLM-1003", model)
    system, first = model.prompts[0]
    assert isinstance(system, SystemMessage)
    assert system.content == client.get("/api/instructions").json()["claim"]
    assert first.content == "Claim CLM-1003"


def test_payment_over_the_limit_is_refused(client):
    model = stub(*decide("approve", 1350.0, pay(1350.0)))
    report = work("CLM-1002", model)
    assert report == "CLM-1002  approve  $1,350.00, waiting for sign-off"

    refusal = model.prompts[-1][-1]
    assert isinstance(refusal, ToolMessage)
    assert refusal.status == "error"
    assert refusal.text == (
        "Refused with status 403: A payout over $1,000.00 needs a handler's sign-off"
    )
    assert client.get("/api/claims/CLM-1002").json()["payment"] is None


def test_an_approval_left_unpaid_says_so():
    report = work("CLM-1001", stub(*decide("approve", 420.0)))
    assert report == "CLM-1001  approve  $420.00, not paid"


@pytest.mark.parametrize("decision", ["decline", "refer"])
def test_declines_and_refers(client, decision):
    report = work("CLM-1003", stub(*decide(decision, 0)))
    assert report == f"CLM-1003  {decision}  $0.00"
    claim = client.get("/api/claims/CLM-1003").json()
    assert claim["status"] == "decided"
    assert claim["payment"] is None


def test_reading_a_section_is_recorded(client):
    model = stub(
        call("read_section", document="claims_manual", number=9),
        call("read_section", document="claims_manual", number=15),
        call("search_documents", query="wild animal"),
        *decide("refer", 0),
    )
    work("CLM-1004", model)

    steps = [(s["kind"], s["content"]) for s in steps_of(client, "CLM-1004")]
    assert steps[0] == (
        "tool_call",
        'read_section(document="claims_manual", number=9)',
    )
    assert steps[1][1].startswith('read_section: {"document": "claims_manual"')
    assert steps[2] == ("reading", "Claims manual, section 9: Repeat claims")
    assert steps[4] == (
        "tool_result",
        "read_section: Refused with status 404: "
        "Section 15 of the claims manual not found",
    )
    assert steps[5] == ("tool_call", 'search_documents(query="wild animal")')
    assert steps[6][1].startswith('search_documents: [{"document": "claims_manual"')
    assert [s for s in steps if s[0] == "reading"] == [steps[2]]


def test_working_out_the_payout(client):
    lines = [
        {
            "description": "Hotel",
            "amount": 245,
            "quantity": 1,
            "kind": "hotel",
            "nights": 1,
            "hours": 0,
        },
        {
            "description": "Meals",
            "amount": 95,
            "quantity": 1,
            "kind": "expense",
            "nights": 0,
            "hours": 0,
        },
        {
            "description": "Taxis",
            "amount": 80,
            "quantity": 1,
            "kind": "expense",
            "nights": 0,
            "hours": 0,
        },
    ]
    model = stub(
        call("calculate_payout", benefit="trip_delay", lines=lines, paid_by_others=0),
        *decide("approve", 420.0, pay(420.0)),
    )
    assert work("CLM-1001", model) == "CLM-1001  approve  $420.00"
    result = steps_of(client, "CLM-1001")[1]
    assert result["kind"] == "tool_result"
    content = result["content"].removeprefix("calculate_payout: ")
    assert json.loads(content)["payout"] == 420.0


def test_a_claim_is_traced_in_the_session_of_its_thread(client, traces):
    work("CLM-1001", stub(*decide("refer", 0)))
    thread_id = client.get("/api/claims/CLM-1001").json()["thread_id"]
    assert [(t["langfuse_session_id"], t["langfuse_trace_name"]) for t in traces] == [
        (f"CLM-1001:{thread_id}", "Work claim")
    ]


def test_a_section_with_bad_arguments_goes_back_to_the_model(client):
    model = stub(
        call("read_section", document="handbook", number=1), *decide("refer", 0)
    )
    assert work("CLM-1004", model) == "CLM-1004  refer  $0.00"
    assert "reading" not in {s["kind"] for s in steps_of(client, "CLM-1004")}


def test_a_provider_error_puts_the_claim_back_in_the_queue(client):
    outage = RuntimeError("503: The model is unavailable")
    report = work("CLM-1004", stub(call("get_claim"), outage))
    assert report == (
        "CLM-1004  failed: RuntimeError: 503: The model is unavailable,"
        " back in the queue"
    )
    claim = client.get("/api/claims/CLM-1004").json()
    assert (claim["status"], claim["attempts"]) == ("waiting", 1)
    last = steps_of(client, "CLM-1004")[-1]
    assert (last["kind"], last["content"]) == (
        "error",
        "RuntimeError: 503: The model is unavailable",
    )

    again = work("CLM-1004", stub(outage))
    assert again.endswith(", left for a handler")
    claim = client.get("/api/claims/CLM-1004").json()
    assert (claim["status"], claim["attempts"]) == ("left_for_handler", 2)


def test_finishing_without_a_decision_is_a_failure(client):
    model = stub(call("get_claim"), AIMessage(content="Hmm."))
    assert work("CLM-1004", model) == (
        "CLM-1004  failed: The agent finished without recording a decision,"
        " back in the queue"
    )


def test_a_claim_agent_going_round_in_circles_stops(client):
    model = StubModel(messages=(call("get_claim") for _ in itertools.count()))
    report = work("CLM-1004", model)
    assert report.startswith("CLM-1004  failed: ModelCallLimitExceededError: ")
    assert report.endswith(", back in the queue")
    assert len(model.prompts) == harness.CLAIM_MODEL_CALLS
    assert client.get("/api/claims/CLM-1004").json()["status"] == "waiting"


def test_a_failure_after_the_decision_keeps_it(client):
    model = stub(
        call("get_claim"),
        record("decline", 0),
        RuntimeError("The connection was lost"),
    )
    assert work("CLM-1003", model) == "CLM-1003  decline  $0.00"
    claim = client.get("/api/claims/CLM-1003").json()
    assert (claim["status"], claim["attempts"]) == ("decided", 1)
    assert "error" not in {s["kind"] for s in steps_of(client, "CLM-1003")}


def test_a_claim_that_isnt_waiting_is_not_started(client):
    work("CLM-1003", stub(*decide("refer", 0)))
    before = steps_of(client, "CLM-1003")
    with pytest.raises(api.Refused, match="^409: Claim CLM-1003 is not waiting$"):
        work("CLM-1003", stub())
    assert steps_of(client, "CLM-1003") == before
    assert client.get("/api/claims/CLM-1003").json()["attempts"] == 1


def test_each_claim_starts_clean(client):
    model = stub(*decide("decline", 0), *decide("refer", 0))
    agent = harness.claim_agent(model)
    harness.work_claim("CLM-1001", agent)
    harness.work_claim("CLM-1003", agent)
    firsts = [prompt for prompt in model.prompts if len(prompt) == 2]
    assert [prompt[1].content for prompt in firsts] == [
        "Claim CLM-1001",
        "Claim CLM-1003",
    ]
    assert firsts[0][0] == firsts[1][0]
    decided = [client.get(f"/api/claims/{i}").json() for i in ("CLM-1001", "CLM-1003")]
    assert [c["decision"]["decision"] for c in decided] == ["decline", "refer"]
    assert decided[0]["thread_id"] != decided[1]["thread_id"]


def test_command_line_works_one_claim(monkeypatch, capsys):
    worked = []
    monkeypatch.setattr(cli, "model", lambda: "model")
    monkeypatch.setattr(cli, "claim_agent", lambda llm: f"agent on {llm}")
    monkeypatch.setattr(cli, "work_claim", lambda *args: worked.append(args))
    cli.main(["CLM-1001"])
    assert worked == [("CLM-1001", "agent on model")]

    def refuse(claim_id, agent):
        raise api.Refused(f"409: Claim {claim_id} is not waiting")

    monkeypatch.setattr(cli, "work_claim", refuse)
    with pytest.raises(SystemExit) as refused:
        cli.main(["CLM-1003"])
    assert refused.value.code == 1
    assert capsys.readouterr().err == (
        "CLM-1003  not started: 409: Claim CLM-1003 is not waiting\n"
    )


def test_model_name(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.delenv("MODEL_NAME", raising=False)
    default = harness.model()
    assert default.model_name == "deepseek/deepseek-v4.1-flash"
    assert default.reasoning_effort == "low"
    assert default.request_timeout == 120
    assert default.max_retries == 5
    monkeypatch.setenv("MODEL_NAME", "openrouter/free")
    assert harness.model().model_name == "openrouter/free"
    assert harness.model().reasoning_effort is None
