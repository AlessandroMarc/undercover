"""A first slice of the UnderCover app.

Run it locally with: uv run uvicorn server:app --reload --env-file .env
On AWS Lambda the entry point is `handler`, at the bottom of this file.

The claims routes need an X-API-Key header that matches UNDERCOVER_API_KEY in the environment.
"""

import os
import secrets

from fastapi import Depends, FastAPI, HTTPException, Security
from fastapi.responses import HTMLResponse
from fastapi.security import APIKeyHeader
from mangum import Mangum
from pydantic import BaseModel

app = FastAPI(title="UnderCover", version="0.1.0")


class Claim(BaseModel):
    claim_id: str
    policy_id: str
    customer: str
    reason: str
    amount: float
    status: str


class Payout(BaseModel):
    amount: float


class PayoutReceipt(BaseModel):
    claim_id: str
    amount: float
    status: str


CLAIMS = {
    "CLM-1001": Claim(
        claim_id="CLM-1001",
        policy_id="POL-2001",
        customer="Maya Patel",
        reason="Flight cancelled by the airline",
        amount=420.00,
        status="open",
    ),
    "CLM-1002": Claim(
        claim_id="CLM-1002",
        policy_id="POL-2002",
        customer="Tom Becker",
        reason="Suitcase lost on a connecting flight",
        amount=1150.00,
        status="open",
    ),
    "CLM-1003": Claim(
        claim_id="CLM-1003",
        policy_id="POL-2003",
        customer="Aiko Tanaka",
        reason="Hospital visit while abroad",
        amount=3800.00,
        status="approved",
    ),
}

HOME_PAGE = """<!doctype html>
<html>
  <head><title>UnderCover</title></head>
  <body style="font-family: sans-serif; margin: 3rem;">
    <h1>UnderCover</h1>
    <p>Travel insurance claims. The dashboard will live here.</p>
    <p><a href="/docs">API docs</a></p>
  </body>
</html>"""


API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(api_key: str | None = Security(API_KEY_HEADER)) -> None:
    """Allow the request only when its X-API-Key header matches the app's key."""
    expected = os.environ.get("UNDERCOVER_API_KEY", "")
    if not expected or not api_key or not secrets.compare_digest(api_key, expected):
        raise HTTPException(status_code=401, detail="Missing or invalid X-API-Key header")


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def home() -> str:
    return HOME_PAGE


@app.get("/health", operation_id="health")
def health() -> dict[str, str]:
    """Check that the UnderCover app is running."""
    return {"status": "ok", "service": "undercover"}


@app.get("/claims", operation_id="list_claims", dependencies=[Depends(require_api_key)])
def list_claims() -> list[Claim]:
    """List every travel insurance claim."""
    return list(CLAIMS.values())


@app.get("/claims/{claim_id}", operation_id="get_claim", dependencies=[Depends(require_api_key)])
def get_claim(claim_id: str) -> Claim:
    """Get one travel insurance claim by its id, such as CLM-1001."""
    if claim_id not in CLAIMS:
        raise HTTPException(status_code=404, detail=f"No claim with id {claim_id}")
    return CLAIMS[claim_id]


@app.post("/claims/{claim_id}/payout", operation_id="approve_payout", dependencies=[Depends(require_api_key)])
def approve_payout(claim_id: str, payout: Payout) -> PayoutReceipt:
    """Approve a claim and pay the customer this amount in dollars."""
    if claim_id not in CLAIMS:
        raise HTTPException(status_code=404, detail=f"No claim with id {claim_id}")
    CLAIMS[claim_id].status = "approved"
    print(f"Paid ${payout.amount:,.2f} on {claim_id}")
    return PayoutReceipt(claim_id=claim_id, amount=payout.amount, status="paid")


handler = Mangum(app)
