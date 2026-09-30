import itertools

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from agent import __main__ as cli
from agent import main
from agent.tools import CLAIM_TOOLS


class StubModel(GenericFakeChatModel):
    """A chat model that gives scripted replies, or raises a scripted error,
    and keeps the prompts it was sent."""

    prompts: list[list[BaseMessage]] = []

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.prompts.append(messages)
        reply = next(self.messages)
        if isinstance(reply, Exception):
            raise reply
        message = AIMessage(content=reply) if isinstance(reply, str) else reply
        return ChatResult(generations=[ChatGeneration(message=message)])


CALL_IDS = itertools.count()


def call(name, text="", **args):
    """A reply that calls one tool, with an id of its own as a real model gives."""
    tool_call = {"name": name, "args": args, "id": f"call-{next(CALL_IDS)}"}
    return AIMessage(content=text, tool_calls=[tool_call])


def record(claim_id, decision, payout):
    return call(
        "record_decision",
        claim_id=claim_id,
        decision=decision,
        payout=payout,
        section="Section 3, Trip Delay",
        reason="The delay was covered.",
    )


def decide(claim_id, decision, payout, *extra):
    return [
        call("get_claim", claim_id=claim_id),
        record(claim_id, decision, payout),
        *extra,
        AIMessage(content=f"Decision: {decision}."),
    ]


def stub(*replies):
    return StubModel(messages=iter(replies))


def pay(claim_id, amount, text=""):
    return call("pay_claim", text=text, claim_id=claim_id, amount=amount)


def steps_of(client, claim_id):
    return client.get(f"/api/claims/{claim_id}/steps").json()


def test_tools_are_named_after_backend_operations(client):
    operations = {
        operation["operationId"]
        for path in client.get("/openapi.json").json()["paths"].values()
        for operation in path.values()
    }
    names = [t.name for t in CLAIM_TOOLS]
    assert names == [
        "get_claim",
        "get_policy",
        "get_claim_history",
        "search_documents",
        "read_section",
        "record_decision",
        "pay_claim",
    ]
    assert set(names) <= operations


def test_approves_and_pays_within_the_limit(client):
    model = stub(
        call("get_claim", claim_id="CLM-1001"),
        call("get_policy", policy_id="POL-2001"),
        call("get_claim_history", customer_id="CUS-3001"),
        record("CLM-1001", "approve", 420.0),
        pay("CLM-1001", 420.0, "Paying now."),
        AIMessage(content="Decision: approve."),
    )
    assert main.work_claim("CLM-1001", model) == "CLM-1001  approve  $420.00"

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
    assert steps[0]["content"] == 'get_claim(claim_id="CLM-1001")'
    assert steps[1]["content"].startswith('get_claim: {"claim_id":"CLM-1001"')
    assert steps[8]["content"] == "Paying now."
    assert steps[9]["content"] == 'pay_claim(claim_id="CLM-1001", amount=420.0)'
    assert steps[-1]["content"] == "Decision: approve."
    assert {s["thread_id"] for s in steps} == {claim["thread_id"]}


def test_uses_the_claim_instructions_from_the_backend(client):
    model = stub(*decide("CLM-1003", "refer", 0))
    main.work_claim("CLM-1003", model)
    system, first = model.prompts[0]
    assert isinstance(system, SystemMessage)
    assert system.content == client.get("/api/instructions").json()["claim"]
    assert first.content == "Claim CLM-1003"


def test_payment_over_the_limit_is_refused(client):
    model = stub(*decide("CLM-1002", "approve", 1350.0, pay("CLM-1002", 1350.0)))
    report = main.work_claim("CLM-1002", model)
    assert report == "CLM-1002  approve  $1,350.00, waiting for sign-off"

    refusal = model.prompts[-1][-1]
    assert isinstance(refusal, ToolMessage)
    assert "needs a handler's sign-off" in refusal.text
    assert refusal.text.startswith("Refused with status 403")
    assert client.get("/api/claims/CLM-1002").json()["payment"] is None


def test_an_approval_left_unpaid_says_so():
    report = main.work_claim("CLM-1001", stub(*decide("CLM-1001", "approve", 420.0)))
    assert report == "CLM-1001  approve  $420.00, not paid"


@pytest.mark.parametrize("decision", ["decline", "refer"])
def test_declines_and_refers(client, decision):
    report = main.work_claim("CLM-1003", stub(*decide("CLM-1003", decision, 0)))
    assert report == f"CLM-1003  {decision}  $0.00"
    claim = client.get("/api/claims/CLM-1003").json()
    assert claim["status"] == "decided"
    assert claim["payment"] is None


def test_reading_a_section_is_recorded(client):
    model = stub(
        call("read_section", document="claims_manual", number=9),
        call("read_section", document="claims_manual", number=15),
        call("search_documents", query="wild animal"),
        *decide("CLM-1004", "refer", 0),
    )
    main.work_claim("CLM-1004", model)

    steps = [(s["kind"], s["content"]) for s in steps_of(client, "CLM-1004")]
    assert steps[0] == (
        "tool_call",
        'read_section(document="claims_manual", number=9)',
    )
    assert steps[1][1].startswith('read_section: {"document":"claims_manual"')
    assert steps[2] == ("reading", "Claims manual, section 9: Repeat claims")
    assert steps[4][1].startswith("read_section: Refused with status 404")
    assert steps[5] == ("tool_call", 'search_documents(query="wild animal")')
    assert steps[6][1].startswith('search_documents: [{"document":"claims_manual"')
    assert [s for s in steps if s[0] == "reading"] == [steps[2]]


def test_a_section_with_bad_arguments_goes_back_to_the_model(client):
    model = stub(
        call("read_section", document="handbook", number=1),
        *decide("CLM-1004", "refer", 0),
    )
    assert main.work_claim("CLM-1004", model) == "CLM-1004  refer  $0.00"
    assert "reading" not in {s["kind"] for s in steps_of(client, "CLM-1004")}


def test_a_provider_error_puts_the_claim_back_in_the_queue(client):
    outage = RuntimeError("503: The model is unavailable")
    model = stub(call("get_claim", claim_id="CLM-1004"), outage)
    report = main.work_claim("CLM-1004", model)
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

    again = main.work_claim("CLM-1004", stub(outage))
    assert again.endswith(", left for a handler")
    claim = client.get("/api/claims/CLM-1004").json()
    assert (claim["status"], claim["attempts"]) == ("left_for_handler", 2)


def test_finishing_without_a_decision_is_a_failure(client):
    model = stub(call("get_claim", claim_id="CLM-1004"), AIMessage(content="Hmm."))
    assert main.work_claim("CLM-1004", model) == (
        "CLM-1004  failed: The agent finished without recording a decision,"
        " back in the queue"
    )


def test_a_claim_agent_going_round_in_circles_stops(client):
    loop = (call("get_claim", claim_id="CLM-1004") for _ in itertools.count())
    model = StubModel(messages=loop)
    report = main.work_claim("CLM-1004", model)
    assert report.startswith("CLM-1004  failed: GraphRecursionError: ")
    assert report.endswith(", back in the queue")
    assert len(model.prompts) == main.STEPS // 2
    assert client.get("/api/claims/CLM-1004").json()["status"] == "waiting"


def test_a_failure_after_the_decision_keeps_it(client):
    model = stub(
        call("get_claim", claim_id="CLM-1003"),
        record("CLM-1003", "decline", 0),
        RuntimeError("The connection was lost"),
    )
    assert main.work_claim("CLM-1003", model) == "CLM-1003  decline  $0.00"
    claim = client.get("/api/claims/CLM-1003").json()
    assert (claim["status"], claim["attempts"]) == ("decided", 1)
    assert "error" not in {s["kind"] for s in steps_of(client, "CLM-1003")}


def test_a_claim_that_isnt_waiting_is_not_started(client):
    main.work_claim("CLM-1003", stub(*decide("CLM-1003", "refer", 0)))
    before = steps_of(client, "CLM-1003")
    report = main.work_claim("CLM-1003", stub())
    assert report == "CLM-1003  not started: 409: Claim CLM-1003 is not waiting"
    assert steps_of(client, "CLM-1003") == before
    assert client.get("/api/claims/CLM-1003").json()["attempts"] == 1


def test_each_claim_starts_clean(client):
    model = stub(*decide("CLM-1001", "decline", 0), *decide("CLM-1003", "refer", 0))
    main.work_claim("CLM-1001", model)
    main.work_claim("CLM-1003", model)
    firsts = [prompt for prompt in model.prompts if len(prompt) == 2]
    assert [prompt[1].content for prompt in firsts] == [
        "Claim CLM-1001",
        "Claim CLM-1003",
    ]
    assert firsts[0][0] == firsts[1][0]
    one = client.get("/api/claims/CLM-1001").json()["thread_id"]
    two = client.get("/api/claims/CLM-1003").json()["thread_id"]
    assert one != two


def test_command_line(monkeypatch, capsys):
    monkeypatch.setattr(cli, "work_claim", lambda claim_id: f"{claim_id}  refer  $0.00")
    cli.main(["CLM-1001"])
    assert capsys.readouterr().out == "CLM-1001  refer  $0.00\n"


def test_model_name(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.delenv("MODEL_NAME", raising=False)
    default = main.model()
    assert default.model_name == "deepseek/deepseek-v4.1-flash"
    assert default.reasoning_effort == "low"
    assert default.request_timeout == 120
    assert default.max_retries == 5
    monkeypatch.setenv("MODEL_NAME", "openrouter/free")
    assert main.model().model_name == "openrouter/free"
    assert main.model().reasoning_effort is None
