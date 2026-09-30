"""The agent's tools, each named after the backend operation it calls."""

from typing import Any, Literal
from urllib.parse import urlencode

import httpx
from langchain_core.tools import tool

BACKEND_URL = "http://localhost:8000"
REFUSED = "Refused with status"


def backend() -> httpx.Client:
    """Return a client for the UnderCover backend."""
    return httpx.Client(base_url=BACKEND_URL, timeout=30)


def request(
    method: str, path: str, body: dict[str, Any] | None = None
) -> httpx.Response:
    """Send one request to the backend."""
    with backend() as client:
        return client.request(method, path, json=body)


def reply(response: httpx.Response) -> str:
    """Give the model the backend's answer, or its reason for refusing."""
    if response.is_success:
        return response.text
    return f"{REFUSED} {response.status_code}: {response.text}"


@tool
def list_claims() -> str:
    """List every claim in the queue, in id order, with its status and decision."""
    return reply(request("GET", "/api/claims"))


@tool
def get_claim(claim_id: str) -> str:
    """Get one claim in full: the story, the items claimed and the documents."""
    return reply(request("GET", f"/api/claims/{claim_id}"))


@tool
def get_policy(policy_id: str) -> str:
    """Get a policy: the plan, add-ons, purchase date, trip and travelers."""
    return reply(request("GET", f"/api/policies/{policy_id}"))


@tool
def get_claim_history(customer_id: str) -> str:
    """Get a customer's earlier claims, with the outcome and the amount paid."""
    return reply(request("GET", f"/api/customers/{customer_id}/claims"))


@tool
def search_documents(query: str) -> str:
    """Search the wording and the manual for one word or a short phrase at a time."""
    return reply(request("GET", f"/api/documents/search?{urlencode({'query': query})}"))


@tool
def read_section(
    document: Literal["policy_wording", "claims_manual"], number: int
) -> str:
    """Read one section of the policy wording or the claims manual in full."""
    return reply(request("GET", f"/api/documents/{document}/sections/{number}"))


@tool
def record_decision(
    claim_id: str,
    decision: Literal["approve", "decline", "refer"],
    payout: float,
    section: str,
    reason: str,
) -> str:
    """Record the decision on a claim; an approval over the limit waits for sign-off."""
    body = {
        "decision": decision,
        "payout": payout,
        "section": section,
        "reason": reason,
    }
    return reply(request("POST", f"/api/claims/{claim_id}/decision", body))


@tool
def pay_claim(claim_id: str, amount: float) -> str:
    """Pay an approved claim its payout, unless it needs a handler's sign-off."""
    return reply(request("POST", f"/api/claims/{claim_id}/payment", {"amount": amount}))


CLAIM_TOOLS = [
    get_claim,
    get_policy,
    get_claim_history,
    search_documents,
    read_section,
    record_decision,
    pay_claim,
]
