"""A handler's sign-off of a held payout: it pays the claim once, commits, then asks
the agent to resume the claim, and stands whatever happens to that call."""

import logging
import threading

import httpx
import pytest

from backend.database import claim_view, claims, engine, payments
from backend.tests.claim_requests import decide, sign_off, start
from backend.tests.rows import count


def held(client, claim_id="CLM-1002", payout=1350.0):
    """Start a claim and approve it over the limit, which holds it for sign-off."""
    start(client, claim_id)
    return decide(client, claim_id, "approve", payout).json()


def as_committed(claim_id):
    """The claim as another connection reads it: what has been committed."""
    with engine().connect() as db:
        query = claim_view.where(claims.c.claim_id == claim_id)
        return db.execute(query).mappings().one()


def test_a_sign_off_pays_the_claim_then_asks_the_agent_to_resume_it(
    client, agent_answers
):
    held(client)
    calls, seen = [], []

    def accept(request):
        calls.append((request.method, request.url.path, request.content))
        claim = as_committed("CLM-1002")
        seen.append((claim["status"], claim["amount"], claim["signed_off_by"]))
        return httpx.Response(202, json={"status": "accepted"})

    agent_answers(accept)
    response = sign_off(client, "CLM-1002")
    assert response.status_code == 200
    claim = response.json()
    assert claim["status"] == "decided"
    assert claim["payment"]["amount"] == 1350.0
    assert claim["decision"]["signed_off_by"] == "Dana Whitfield"
    assert claim["decision"]["signed_off_at"] is not None
    assert calls == [("POST", "/api/claims/CLM-1002/resume", b"")]
    assert seen == [("decided", 1350.0, "Dana Whitfield")]


def unreachable(request):
    raise httpx.ConnectError("Connection refused")


def slow(request):
    raise httpx.ReadTimeout("Timed out")


def refusing(request):
    detail = "Claim CLM-1002 isn't paused for a handler"
    return httpx.Response(409, json={"detail": detail})


def broken(request):
    return httpx.Response(500, text="Internal Server Error")


@pytest.mark.parametrize("answer", [unreachable, slow, refusing, broken])
def test_a_sign_off_stands_whatever_happens_to_the_call(
    client, agent_answers, caplog, answer
):
    held(client)
    agent_answers(answer)
    response = sign_off(client, "CLM-1002")
    assert response.status_code == 200
    assert response.json()["payment"]["amount"] == 1350.0
    assert as_committed("CLM-1002")["status"] == "decided"
    [warning] = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert warning.getMessage().startswith("CLM-1002 wasn't resumed: ")


def test_two_sign_offs_at_the_same_moment_pay_the_claim_once(client, agent_calls):
    held(client)
    together = threading.Barrier(2)
    answers = []

    def sign():
        together.wait()
        answers.append(sign_off(client, "CLM-1002"))

    signing = [threading.Thread(target=sign) for _ in range(2)]
    for thread in signing:
        thread.start()
    for thread in signing:
        thread.join(10)
    assert sorted(a.status_code for a in answers) == [200, 409]
    [refused] = [a for a in answers if a.status_code == 409]
    assert refused.json()["detail"] == "Claim CLM-1002 is not waiting for sign-off"
    assert count(payments) == 1
    assert agent_calls == [("/api/claims/CLM-1002/resume", None)]
