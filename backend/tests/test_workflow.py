import sqlite3
from contextlib import closing

import pytest

from backend.tests.claim_requests import decide, pay, sign_off, start


def test_start_claim(client):
    response = start(client, "CLM-1001")
    assert response.status_code == 200
    assert response.json()["status"] == "in_progress"
    assert response.json()["thread_id"] == "t-1"
    assert start(client, "CLM-1001").status_code == 409


def test_start_needs_a_thread_id(client):
    response = client.post("/api/claims/CLM-1001/start", json={"thread_id": ""})
    assert response.status_code == 422


def test_steps(client):
    assert (
        client.post(
            "/api/claims/CLM-1001/steps", json={"kind": "message", "content": "Hi"}
        ).status_code
        == 409
    )
    start(client, "CLM-1001")
    for kind, content in (("tool_call", "get_claim"), ("tool_result", "{}")):
        response = client.post(
            "/api/claims/CLM-1001/steps", json={"kind": kind, "content": content}
        )
        assert response.status_code == 200
    steps = client.get("/api/claims/CLM-1001/steps").json()
    assert [(s["kind"], s["content"]) for s in steps] == [
        ("tool_call", "get_claim"),
        ("tool_result", "{}"),
    ]
    assert steps[0]["step_id"] < steps[1]["step_id"]
    assert all(s["thread_id"] == "t-1" and s["created_at"] for s in steps)
    assert client.get("/api/claims/CLM-1002/steps").json() == []
    assert client.get("/api/claims/CLM-9999/steps").status_code == 404


def test_step_kind_must_be_known(client):
    start(client, "CLM-1001")
    response = client.post(
        "/api/claims/CLM-1001/steps", json={"kind": "thought", "content": "Hmm"}
    )
    assert response.status_code == 422


def test_decision_needs_a_claim_in_progress(client):
    assert decide(client, "CLM-1001", "decline", 0).status_code == 409
    assert decide(client, "CLM-9999", "decline", 0).status_code == 404


@pytest.mark.parametrize(
    ("decision", "payout", "section"),
    [
        ("approve", 0, "Section 3"),
        ("decline", 50, "Section 3"),
        ("refer", 10, "Section 3"),
        ("maybe", 0, "Section 3"),
        ("approve", -5, "Section 3"),
        ("decline", 0, ""),
    ],
)
def test_invalid_decisions(client, decision, payout, section):
    start(client, "CLM-1001")
    response = client.post(
        "/api/claims/CLM-1001/decision",
        json={
            "decision": decision,
            "payout": payout,
            "section": section,
            "reason": "Because.",
        },
    )
    assert response.status_code == 422
    assert client.get("/api/claims/CLM-1001").json()["decision"] is None


def test_approve_and_pay_within_the_limit(client):
    start(client, "CLM-1001")
    claim = decide(client, "CLM-1001", "approve", 420.0).json()
    assert claim["status"] == "decided"
    assert claim["decision"]["payout"] == 420.0
    assert claim["payment"] is None
    response = pay(client, "CLM-1001", 420.0)
    assert response.status_code == 200
    assert response.json()["amount"] == 420.0
    assert response.json()["signed_off_by"] is None
    assert client.get("/api/claims/CLM-1001").json()["payment"]["amount"] == 420.0
    assert pay(client, "CLM-1001", 420.0).status_code == 409


def test_queue_shows_the_decision(client):
    start(client, "CLM-1001")
    decide(client, "CLM-1001", "approve", 420.0)
    first = client.get("/api/claims").json()[0]
    assert (first["status"], first["decision"], first["payout"]) == (
        "decided",
        "approve",
        420.0,
    )


def test_payment_must_match_the_payout(client):
    start(client, "CLM-1001")
    decide(client, "CLM-1001", "approve", 420.0)
    response = pay(client, "CLM-1001", 500.0)
    assert response.status_code == 422
    assert (
        response.json()["detail"] == "The amount must be the approved payout of $420.00"
    )
    assert client.get("/api/claims/CLM-1001").json()["payment"] is None


def test_exactly_the_limit_needs_no_sign_off(client):
    start(client, "CLM-1002")
    assert decide(client, "CLM-1002", "approve", 1000.0).json()["status"] == "decided"
    assert pay(client, "CLM-1002", 1000.0).status_code == 200


def test_over_the_limit_waits_for_sign_off(client):
    start(client, "CLM-1002")
    claim = decide(client, "CLM-1002", "approve", 1350.0).json()
    assert claim["status"] == "waiting_for_sign_off"
    response = pay(client, "CLM-1002", 1350.0)
    assert response.status_code == 403
    assert response.json()["detail"] == (
        "A payout over $1,000.00 needs a handler's sign-off"
    )
    assert client.get("/api/claims/CLM-1002").json()["payment"] is None


def test_sign_off(client):
    start(client, "CLM-1002")
    decide(client, "CLM-1002", "approve", 1350.0)
    assert sign_off(client, "CLM-1002", "HND-99").status_code == 404
    claim = sign_off(client, "CLM-1002", "HND-01").json()
    assert claim["status"] == "decided"
    assert claim["payment"]["amount"] == 1350.0
    assert claim["payment"]["signed_off_by"] == "Dana Whitfield"
    assert pay(client, "CLM-1002", 1350.0).status_code == 409
    assert sign_off(client, "CLM-1002", "HND-01").status_code == 409


def test_sign_off_needs_a_claim_waiting_for_it(client):
    assert sign_off(client, "CLM-1001", "HND-01").status_code == 409
    start(client, "CLM-1001")
    decide(client, "CLM-1001", "approve", 420.0)
    assert sign_off(client, "CLM-1001", "HND-01").status_code == 409


def test_sign_off_needs_a_handler_who_can_approve(client, database):
    with closing(sqlite3.connect(database)) as db, db:
        db.execute("UPDATE handlers SET can_approve_over_limit = 0")
    start(client, "CLM-1002")
    decide(client, "CLM-1002", "approve", 1350.0)
    response = sign_off(client, "CLM-1002", "HND-02")
    assert response.status_code == 403
    assert response.json()["detail"] == (
        "Marcus Oyelaran can't sign off payouts over $1,000.00"
    )


@pytest.mark.parametrize("decision", ["decline", "refer"])
def test_declines_and_referrals_are_decided_and_unpaid(client, decision):
    start(client, "CLM-1003")
    claim = decide(client, "CLM-1003", decision, 0).json()
    assert claim["status"] == "decided"
    assert claim["decision"]["decision"] == decision
    assert pay(client, "CLM-1003", 10.0).status_code == 409


def test_pay_needs_an_approval(client):
    start(client, "CLM-1001")
    assert pay(client, "CLM-1001", 420.0).status_code == 409


def test_list_handlers(client):
    handlers = client.get("/api/handlers").json()
    assert [h["name"] for h in handlers] == [
        "Dana Whitfield",
        "Marcus Oyelaran",
        "Priya Raman",
    ]
    assert all(h["can_approve_over_limit"] for h in handlers)
