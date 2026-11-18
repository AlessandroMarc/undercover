from pathlib import Path

from langchain_core.messages import AIMessage

from agent import harness, main
from agent.tests.stubs import calls, decision, stub


def test_approve_under_the_limit_and_pay(api):
    llm = stub(
        calls(("get_claim", {"claim_id": "CLM-1001"})),
        calls(decision("CLM-1001", "approve", 420.0)),
        calls(("pay_claim", {"claim_id": "CLM-1001", "amount": 420.0})),
        AIMessage(content="Approved for $420.00."),
    )
    assert main.run("CLM-1001", "thread-1", llm) == "Approved for $420.00."
    claim = api.get("/api/claims/CLM-1001").json()
    assert claim["status"] == "decided"
    assert claim["decision"]["decision"] == "approve"
    assert claim["payment"]["amount"] == 420.0
    steps = api.get("/api/claims/CLM-1001/steps").json()
    kinds = [step["kind"] for step in steps]
    assert kinds == ["tool_call", "tool_result"] * 3 + ["message"]
    assert steps[0]["text"] == "get_claim(claim_id='CLM-1001')"
    assert steps[1]["text"].startswith("get_claim: ")


def test_reading_a_section_is_recorded_as_a_read_step(api):
    llm = stub(
        calls(("search_sections", {"query": "meals"})),
        calls(("read_section", {"document": "claims-manual", "number": 10})),
        calls(("read_section", {"document": "claims-manual", "number": 99})),
        AIMessage(content="Looked it up."),
    )
    main.run("CLM-1001", "thread-read", llm)
    steps = api.get("/api/claims/CLM-1001/steps").json()
    reads = [step["text"] for step in steps if step["kind"] == "read"]
    assert reads == ["Claims manual, 10. Meals without receipts"]
    assert any(
        step["kind"] == "tool_result" and step["text"].startswith("read_section: Error")
        for step in steps
    )


def test_a_payout_over_the_limit_is_blocked(api):
    llm = stub(
        calls(decision("CLM-1002", "approve", 1250.0)),
        calls(("pay_claim", {"claim_id": "CLM-1002", "amount": 1250.0})),
        AIMessage(content="Approved, waiting for sign-off."),
    )
    main.run("CLM-1002", "thread-2", llm)
    claim = api.get("/api/claims/CLM-1002").json()
    assert claim["status"] == "awaiting_signoff"
    assert claim["payment"] is None
    steps = api.get("/api/claims/CLM-1002/steps").json()
    refusal = [
        step for step in steps if step["text"].startswith("pay_claim: Error 409")
    ]
    assert len(refusal) == 1
    assert "sign-off" in refusal[0]["text"]


def test_decline_leaves_no_payment(api):
    llm = stub(
        calls(decision("CLM-1003", "decline", 0.0)),
        AIMessage(content="Declined."),
    )
    main.run("CLM-1003", "thread-3", llm)
    claim = api.get("/api/claims/CLM-1003").json()
    assert claim["status"] == "decided"
    assert claim["decision"]["decision"] == "decline"
    assert claim["payment"] is None


def test_the_instructions_come_from_the_api(api, monkeypatch):
    seen = {}
    real = main.create_agent

    def spy(*args, **kwargs):
        seen.update(kwargs)
        return real(*args, **kwargs)

    monkeypatch.setattr(main, "create_agent", spy)
    main.run("CLM-1001", "thread-4", stub(AIMessage(content="Nothing to do.")))
    assert seen["system_prompt"] == api.get("/api/instructions/claim").text


def test_tools_return_data_and_refusals_as_text(api):
    assert "Maya Patel" in main.get_customer.invoke({"customer_id": "CUS-3001"})
    assert '"plan":"premium"' in main.get_policy.invoke({"policy_id": "POL-2001"})
    assert main.get_plan.invoke({"plan": "premium"}).startswith('{"plan":"premium"')
    sections = main.list_sections.invoke({"document": "policy-wording"})
    assert "Your plan" in sections
    assert "Meals without receipts" in main.read_section.invoke(
        {"document": "claims-manual", "number": 10}
    )
    assert "Repeat claims" in main.search_sections.invoke({"query": "third claim"})
    assert main.get_claim.invoke({"claim_id": "CLM-0000"}).startswith("Error 404")


def test_the_agent_reads_no_files():
    for module in (main, harness):
        source = Path(str(module.__file__)).read_text(encoding="utf-8")
        for forbidden in ("data/", "read_text", "open(", "evals"):
            assert forbidden not in source, (module.__name__, forbidden)


def test_model_name(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.delenv("MODEL_NAME", raising=False)
    assert main.model().model_name == "deepseek/deepseek-v4.1-flash"
    monkeypatch.setenv("MODEL_NAME", "openrouter/free")
    assert main.model().model_name == "openrouter/free"
