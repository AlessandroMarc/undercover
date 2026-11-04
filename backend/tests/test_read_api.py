from backend.db import connect
from backend.seed import seed


def test_queue_is_seeded_and_waiting(client):
    claims = client.get("/api/claims").json()
    assert len(claims) == 25
    assert {claim["status"] for claim in claims} == {"waiting"}
    first = claims[0]
    assert first["claim_id"] == "CLM-1001"
    assert first["customer_name"] == "Maya Patel"
    assert first["decision"] is None


def test_get_claim(client):
    claim = client.get("/api/claims/CLM-1001").json()
    assert claim["claim_type"] == "trip_delay"
    assert claim["amount_claimed"] == 420.0
    assert len(claim["items"]) == 3
    assert claim["documents"][0]["type"] == "carrier_report"
    assert claim["status"] == "waiting"
    assert claim["decision"] is None


def test_get_policy(client):
    policy = client.get("/api/policies/POL-2001").json()
    assert policy["plan"] == "premium"
    assert policy["add_ons"] == []
    assert policy["purchased_on"] == "2026-04-22"
    assert policy["trip"]["destination"] == "Rome, Italy"
    assert policy["travelers"] == ["Maya Patel"]


def test_get_plan(client):
    plan = client.get("/api/plans/premium").json()
    assert plan["per_item_limit"] == 300.0
    assert plan["deductible"] == 50.0


def test_get_customer_has_history_but_no_contact_details(client):
    response = client.get("/api/customers/CUS-3001")
    customer = response.json()
    assert customer["previous_claims"][0]["claim_id"] == "CLM-0412"
    for private in ("email", "phone", "date_of_birth", "address"):
        assert private not in customer


def test_get_policy_wording(client):
    response = client.get("/api/policy-wording")
    assert response.text.startswith("# UnderCover Travel Insurance: Policy Wording")


def test_get_instructions(client):
    assert client.get("/api/instructions").text.strip()


def test_list_handlers(client):
    handlers = client.get("/api/handlers").json()
    assert [handler["handler_id"] for handler in handlers] == [
        "HND-01",
        "HND-02",
        "HND-03",
    ]


def test_unknown_ids_return_404(client):
    for path in (
        "/api/claims/CLM-0000",
        "/api/policies/POL-0000",
        "/api/customers/CUS-0000",
        "/api/plans/gold",
    ):
        assert client.get(path).status_code == 404


def test_restart_keeps_the_data(client):
    conn = connect()
    seed(conn)
    conn.close()
    assert len(client.get("/api/claims").json()) == 25
