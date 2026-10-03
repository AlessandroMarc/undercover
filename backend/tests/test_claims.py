from backend import seed


def test_list_claims(client):
    claims = client.get("/api/claims").json()
    assert len(claims) == 25
    assert [claim["claim_id"] for claim in claims] == sorted(
        claim["claim_id"] for claim in claims
    )
    assert {claim["status"] for claim in claims} == {"waiting"}
    assert claims[0] == {
        "claim_id": "CLM-1001",
        "customer_name": "Maya Patel",
        "claim_type": "trip_delay",
        "summary": "Flight home canceled by the airline, rebooked the next morning",
        "amount_claimed": 420.0,
        "submitted_on": "2026-06-24",
        "status": "waiting",
        "decision": None,
        "payout": None,
    }


def test_get_claim(client):
    claim = client.get("/api/claims/CLM-1001").json()
    assert claim["customer_name"] == "Maya Patel"
    assert claim["story"].startswith("My flight home from Rome")
    assert len(claim["items"]) == 3
    assert len(claim["documents"]) == 4
    assert claim["status"] == "waiting"
    assert claim["decision"] is None
    assert claim["payment"] is None


def test_get_policy(client):
    policy = client.get("/api/policies/POL-2001").json()
    assert policy["plan"] == "premium"
    assert policy["add_ons"] == []
    assert policy["trip"]["destination"] == "Rome, Italy"
    assert policy["trip"]["returns_on"] == "2026-06-18"


def test_get_claim_history_leaves_out_personal_details(client):
    response = client.get("/api/customers/CUS-3001/claims")
    history = response.json()
    assert [claim["claim_id"] for claim in history] == ["CLM-0412"]
    for field in ("email", "phone", "address", "date_of_birth"):
        assert field not in response.text


def test_unknown_ids(client):
    for path in (
        "/api/claims/CLM-9999",
        "/api/policies/POL-9999",
        "/api/customers/CUS-9999/claims",
    ):
        response = client.get(path)
        assert response.status_code == 404
        assert "9999 not found" in response.json()["detail"]


def test_seed_command(capsys):
    seed.main()
    assert capsys.readouterr().out == (
        "Seeded 25 claims, 50 policies, 49 customers and 3 handlers "
        "into undercover.db\n"
    )
