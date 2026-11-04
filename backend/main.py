"""The UnderCover backend."""

import json
import sqlite3
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import PlainTextResponse

from backend.db import connect, get_db
from backend.models import (
    Claim,
    ClaimSummary,
    Customer,
    Decision,
    Handler,
    NewPayment,
    NewSignOff,
    NewStep,
    Payment,
    Plan,
    Policy,
    SignOff,
    Step,
)
from backend.seed import seed

Db = Annotated[sqlite3.Connection, Depends(get_db)]

DOCUMENT_QUERIES = {
    "policies": "SELECT body FROM policies WHERE id = ?",
    "customers": "SELECT body FROM customers WHERE id = ?",
    "plans": "SELECT body FROM plans WHERE id = ?",
    "handlers": "SELECT body FROM handlers WHERE id = ?",
}


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    conn = connect()
    seed(conn)
    conn.close()
    yield


app = FastAPI(title="UnderCover", lifespan=lifespan)


def document(
    db: sqlite3.Connection,
    table: Literal["policies", "customers", "plans", "handlers"],
    key: str,
) -> str:
    row = db.execute(DOCUMENT_QUERIES[table], (key,)).fetchone()
    if row is None:
        raise HTTPException(404, f"{key} not found")
    return row["body"]


def setting(db: sqlite3.Connection, key: str) -> str:
    return db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()[0]


def payout_limit(db: sqlite3.Connection) -> float:
    return float(setting(db, "payout_approval_limit"))


@app.get("/api/health", operation_id="health")
def health() -> dict[str, str]:
    """Check that the backend is running."""
    return {"status": "ok"}


@app.get("/api/claims", operation_id="list_claims")
def list_claims(db: Db) -> list[ClaimSummary]:
    """List every claim in the queue with its status."""
    rows = db.execute(
        "SELECT claim_id, status, decision, payout, body,"
        " (SELECT json_extract(body, '$.name') FROM customers"
        "  WHERE id = claims.customer_id) AS customer_name"
        " FROM claims ORDER BY claim_id"
    ).fetchall()
    summaries = []
    for row in rows:
        body = json.loads(row["body"])
        summaries.append(
            ClaimSummary(
                claim_id=row["claim_id"],
                customer_name=row["customer_name"],
                claim_type=body["claim_type"],
                summary=body["summary"],
                amount_claimed=body["amount_claimed"],
                status=row["status"],
                decision=row["decision"],
                payout=row["payout"],
            )
        )
    return summaries


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def claim_row(db: sqlite3.Connection, claim_id: str) -> sqlite3.Row:
    row = db.execute("SELECT * FROM claims WHERE claim_id = ?", (claim_id,)).fetchone()
    if row is None:
        raise HTTPException(404, f"{claim_id} not found")
    return row


def build_claim(db: sqlite3.Connection, row: sqlite3.Row) -> Claim:
    decision = None
    if row["decision"]:
        decision = Decision(
            decision=row["decision"],
            payout=row["payout"],
            explanation=row["explanation"],
            policy_section=row["policy_section"],
        )
    payment = db.execute(
        "SELECT amount, paid_on FROM payments WHERE claim_id = ?", (row["claim_id"],)
    ).fetchone()
    sign_off = None
    if row["signed_off_by"]:
        handler = Handler.model_validate_json(
            document(db, "handlers", row["signed_off_by"])
        )
        sign_off = SignOff(
            handler_id=handler.handler_id,
            handler_name=handler.name,
            signed_off_on=row["signed_off_on"],
        )
    return Claim(
        **json.loads(row["body"]),
        status=row["status"],
        decision=decision,
        payment=Payment(**payment) if payment else None,
        sign_off=sign_off,
    )


def record_payment(db: sqlite3.Connection, claim_id: str, amount: float) -> Payment:
    paid_on = now()
    db.execute("INSERT INTO payments VALUES (?, ?, ?)", (claim_id, amount, paid_on))
    return Payment(amount=amount, paid_on=paid_on)


@app.get("/api/claims/{claim_id}", operation_id="get_claim")
def get_claim(claim_id: str, db: Db) -> Claim:
    """Get one claim in full, with its status, decision, payment and sign-off."""
    return build_claim(db, claim_row(db, claim_id))


@app.post("/api/claims/{claim_id}/start", operation_id="start_claim")
def start_claim(claim_id: str, db: Db) -> Claim:
    """Mark a claim as in progress when the agent starts work on it."""
    row = claim_row(db, claim_id)
    if row["status"] in ("awaiting_signoff", "decided"):
        raise HTTPException(409, f"{claim_id} is already decided")
    with db:
        db.execute(
            "UPDATE claims SET status = 'in_progress' WHERE claim_id = ?", (claim_id,)
        )
    return build_claim(db, claim_row(db, claim_id))


@app.get("/api/claims/{claim_id}/steps", operation_id="list_steps")
def list_steps(claim_id: str, db: Db) -> list[Step]:
    """List what the agent did on a claim, oldest first."""
    claim_row(db, claim_id)
    rows = db.execute(
        "SELECT id, kind, text, created_at FROM steps WHERE claim_id = ? ORDER BY id",
        (claim_id,),
    ).fetchall()
    return [Step(**row) for row in rows]


@app.post("/api/claims/{claim_id}/steps", operation_id="add_step")
def add_step(claim_id: str, step: NewStep, db: Db) -> Step:
    """Record one step the agent took on a claim."""
    claim_row(db, claim_id)
    created_at = now()
    with db:
        cursor = db.execute(
            "INSERT INTO steps (claim_id, kind, text, created_at) VALUES (?, ?, ?, ?)",
            (claim_id, step.kind, step.text, created_at),
        )
    return Step(id=cursor.lastrowid or 0, created_at=created_at, **step.model_dump())


@app.post("/api/claims/{claim_id}/decision", operation_id="decide_claim")
def decide_claim(claim_id: str, decision: Decision, db: Db) -> Claim:
    """Record the agent's decision, holding the payment above the approval limit."""
    row = claim_row(db, claim_id)
    if row["status"] in ("awaiting_signoff", "decided"):
        raise HTTPException(409, f"{claim_id} is already decided")
    if (decision.decision == "approve") != (decision.payout > 0):
        raise HTTPException(
            422, "Only an approval has a payout, and it must be above zero"
        )
    over_limit = decision.payout > payout_limit(db)
    status = "awaiting_signoff" if over_limit else "decided"
    with db:
        db.execute(
            "UPDATE claims SET status = ?, decision = ?, payout = ?, explanation = ?,"
            " policy_section = ? WHERE claim_id = ?",
            (
                status,
                decision.decision,
                decision.payout,
                decision.explanation,
                decision.policy_section,
                claim_id,
            ),
        )
    return build_claim(db, claim_row(db, claim_id))


@app.post("/api/claims/{claim_id}/payment", operation_id="pay_claim")
def pay_claim(claim_id: str, payment: NewPayment, db: Db) -> Payment:
    """Pay an approved claim, refusing a payout over the limit before sign-off."""
    row = claim_row(db, claim_id)
    if row["decision"] != "approve":
        raise HTTPException(409, f"{claim_id} is not approved")
    if row["payout"] > payout_limit(db) and not row["signed_off_by"]:
        raise HTTPException(
            409, f"{claim_id} needs a handler's sign-off before payment"
        )
    if payment.amount != row["payout"]:
        raise HTTPException(409, f"The approved payout is {row['payout']:.2f}")
    if db.execute("SELECT 1 FROM payments WHERE claim_id = ?", (claim_id,)).fetchone():
        raise HTTPException(409, f"{claim_id} is already paid")
    with db:
        return record_payment(db, claim_id, payment.amount)


@app.post("/api/claims/{claim_id}/sign-off", operation_id="sign_off_claim")
def sign_off_claim(claim_id: str, sign_off: NewSignOff, db: Db) -> Claim:
    """Let a handler sign off a payout over the limit, which releases the payment."""
    row = claim_row(db, claim_id)
    handler = Handler.model_validate_json(document(db, "handlers", sign_off.handler_id))
    if not handler.can_approve_over_limit:
        raise HTTPException(
            403, f"{handler.name} cannot sign off payouts over the limit"
        )
    if row["status"] != "awaiting_signoff":
        raise HTTPException(409, f"{claim_id} is not waiting for sign-off")
    with db:
        db.execute(
            "UPDATE claims SET status = 'decided', signed_off_by = ?, signed_off_on = ?"
            " WHERE claim_id = ?",
            (handler.handler_id, now(), claim_id),
        )
        record_payment(db, claim_id, row["payout"])
    return build_claim(db, claim_row(db, claim_id))


@app.get("/api/policies/{policy_id}", operation_id="get_policy")
def get_policy(policy_id: str, db: Db) -> Policy:
    """Get a policy with its plan, add-ons, trip and travelers."""
    return Policy.model_validate_json(document(db, "policies", policy_id))


@app.get("/api/customers/{customer_id}", operation_id="get_customer")
def get_customer(customer_id: str, db: Db) -> Customer:
    """Get a customer's name and claim history, without contact details."""
    return Customer.model_validate_json(document(db, "customers", customer_id))


@app.get("/api/plans/{plan}", operation_id="get_plan")
def get_plan(plan: str, db: Db) -> Plan:
    """Get a plan's limits, waiting periods and deductible."""
    return Plan.model_validate_json(document(db, "plans", plan))


@app.get(
    "/api/policy-wording",
    operation_id="get_policy_wording",
    response_class=PlainTextResponse,
)
def get_policy_wording(db: Db) -> str:
    """Get the policy wording, the contract with the customer."""
    return setting(db, "policy_wording")


@app.get(
    "/api/instructions",
    operation_id="get_instructions",
    response_class=PlainTextResponse,
)
def get_instructions(db: Db) -> str:
    """Get the UnderCover Agent's instructions."""
    return setting(db, "instructions")


@app.get("/api/handlers", operation_id="list_handlers")
def list_handlers(db: Db) -> list[Handler]:
    """List the claims handlers."""
    rows = db.execute("SELECT body FROM handlers ORDER BY id").fetchall()
    return [Handler.model_validate_json(row["body"]) for row in rows]
