CLAIM = "CLM-1001"


def decide(client, decision="approve", payout=420.0, claim_id=CLAIM):
    return client.post(
        f"/api/claims/{claim_id}/decision",
        json={
            "decision": decision,
            "payout": payout,
            "explanation": "Covered under the plan.",
            "policy_section": "3. Trip Delay",
        },
    )


def pay(client, amount, claim_id=CLAIM):
    return client.post(f"/api/claims/{claim_id}/payment", json={"amount": amount})


def sign_off(client, handler_id="HND-01", claim_id=CLAIM):
    return client.post(
        f"/api/claims/{claim_id}/sign-off", json={"handler_id": handler_id}
    )


def status(client, claim_id=CLAIM):
    return client.get(f"/api/claims/{claim_id}").json()["status"]


def test_start_claim(client):
    response = client.post(f"/api/claims/{CLAIM}/start")
    assert response.json()["status"] == "in_progress"
    assert client.post(f"/api/claims/{CLAIM}/start").status_code == 200
    assert client.post("/api/claims/CLM-0000/start").status_code == 404


def test_steps_come_back_in_order_with_timestamps(client):
    for text in ("one", "two", "three"):
        response = client.post(
            f"/api/claims/{CLAIM}/steps", json={"kind": "message", "text": text}
        )
        assert response.json()["text"] == text
    steps = client.get(f"/api/claims/{CLAIM}/steps").json()
    assert [step["text"] for step in steps] == ["one", "two", "three"]
    assert all(step["created_at"] for step in steps)
    assert client.get("/api/claims/CLM-0000/steps").status_code == 404
    missing = client.post(
        "/api/claims/CLM-0000/steps", json={"kind": "message", "text": "x"}
    )
    assert missing.status_code == 404


def test_approve_under_the_limit_then_pay(client):
    client.post(f"/api/claims/{CLAIM}/start")
    claim = decide(client).json()
    assert claim["status"] == "decided"
    assert claim["decision"]["policy_section"] == "3. Trip Delay"
    assert pay(client, 420.0).status_code == 200
    claim = client.get(f"/api/claims/{CLAIM}").json()
    assert claim["payment"]["amount"] == 420.0
    assert claim["sign_off"] is None


def test_approve_over_the_limit_blocks_payment(client):
    assert decide(client, payout=1250.0).json()["status"] == "awaiting_signoff"
    response = pay(client, 1250.0)
    assert response.status_code == 409
    assert "sign-off" in response.json()["detail"]
    assert client.get(f"/api/claims/{CLAIM}").json()["payment"] is None
    assert status(client) == "awaiting_signoff"


def test_payout_exactly_at_the_limit_needs_no_sign_off(client):
    assert decide(client, payout=1000.0).json()["status"] == "decided"
    assert pay(client, 1000.0).status_code == 200


def test_sign_off_releases_the_payment(client):
    decide(client, payout=1250.0)
    claim = sign_off(client, "HND-02").json()
    assert claim["status"] == "decided"
    assert claim["sign_off"]["handler_name"] == "Marcus Oyelaran"
    assert claim["payment"]["amount"] == 1250.0
    assert pay(client, 1250.0).status_code == 409


def test_sign_off_refusals(client):
    assert sign_off(client).status_code == 409
    decide(client, payout=1250.0)
    assert sign_off(client, "HND-99").status_code == 404
    assert sign_off(client, claim_id="CLM-0000").status_code == 404
    assert status(client) == "awaiting_signoff"


def test_payment_refusals(client):
    assert pay(client, 100.0).status_code == 409
    decide(client, payout=420.0)
    assert pay(client, 400.0).status_code == 409
    assert pay(client, 420.0).status_code == 200
    assert pay(client, 420.0).status_code == 409


def test_no_payment_on_declined_or_referred_claims(client):
    decide(client, "decline", 0.0)
    assert pay(client, 100.0).status_code == 409
    decide(client, "refer", 0.0, "CLM-1002")
    assert pay(client, 100.0, "CLM-1002").status_code == 409
    assert status(client) == "decided"
    assert status(client, "CLM-1002") == "decided"
    assert client.get(f"/api/claims/{CLAIM}").json()["payment"] is None


def test_decision_refusals(client):
    assert decide(client, "decline", 100.0).status_code == 422
    assert decide(client, "approve", 0.0).status_code == 422
    assert decide(client, claim_id="CLM-0000").status_code == 404
    assert decide(client).status_code == 200
    assert decide(client).status_code == 409
    assert client.post(f"/api/claims/{CLAIM}/start").status_code == 409


def test_queue_shows_the_decision(client):
    decide(client, payout=420.0)
    first = client.get("/api/claims").json()[0]
    assert (first["status"], first["decision"], first["payout"]) == (
        "decided",
        "approve",
        420.0,
    )
