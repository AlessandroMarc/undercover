"""The UnderCover backend."""

import json
import sqlite3
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
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
    Plan,
    Policy,
)
from backend.seed import seed

Db = Annotated[sqlite3.Connection, Depends(get_db)]

DOCUMENT_QUERIES = {
    "policies": "SELECT body FROM policies WHERE id = ?",
    "customers": "SELECT body FROM customers WHERE id = ?",
    "plans": "SELECT body FROM plans WHERE id = ?",
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
    table: Literal["policies", "customers", "plans"],
    key: str,
) -> str:
    row = db.execute(DOCUMENT_QUERIES[table], (key,)).fetchone()
    if row is None:
        raise HTTPException(404, f"{key} not found")
    return row["body"]


def setting(db: sqlite3.Connection, key: str) -> str:
    return db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()[0]


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


@app.get("/api/claims/{claim_id}", operation_id="get_claim")
def get_claim(claim_id: str, db: Db) -> Claim:
    """Get one claim in full, with its status and the agent's decision."""
    row = db.execute("SELECT * FROM claims WHERE claim_id = ?", (claim_id,)).fetchone()
    if row is None:
        raise HTTPException(404, f"{claim_id} not found")
    decision = None
    if row["decision"]:
        decision = Decision(
            decision=row["decision"],
            payout=row["payout"],
            explanation=row["explanation"],
            policy_section=row["policy_section"],
        )
    return Claim(**json.loads(row["body"]), status=row["status"], decision=decision)


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
