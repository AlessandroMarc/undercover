from agent.tools import CLAIM_TOOLS, QUEUE_TOOLS


def operations(client):
    """Return the operation ids of the backend's API."""
    paths = client.get("/openapi.json").json()["paths"].values()
    return {operation["operationId"] for path in paths for operation in path.values()}


def test_claim_tools_are_named_after_backend_operations(client):
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
    assert set(names) <= operations(client)


def test_queue_tools_are_named_after_backend_operations_or_hand_claims_on(client):
    names = [t.name for t in QUEUE_TOOLS]
    assert names == ["list_claims", "write_todos", "work_claim"]
    assert {"list_claims", "write_todos"} <= operations(client)


def test_a_claim_agent_can_only_act_on_its_own_claim():
    assert all("claim_id" not in t.args for t in CLAIM_TOOLS)
