"""The UnderCover backend's API: one function for each operation the agent uses."""

import os
from typing import Any, Literal, TypedDict

import httpx

BACKEND_URL = os.getenv("UNDERCOVER_API", "http://127.0.0.1:8000")

backend = httpx.Client(base_url=f"{BACKEND_URL}/api", timeout=30)

DecisionKind = Literal["approve", "decline", "refer"]
DocumentName = Literal["policy_wording", "claims_manual"]
StepKind = Literal["tool_call", "tool_result", "message", "reading"]


class Todo(TypedDict):
    content: str
    status: Literal["to_do", "in_progress", "done", "left_for_handler"]


class Refused(Exception):
    """The backend refused a request, with its status code and reason."""


def _call(method: str, path: str, **request: Any) -> Any:
    """Send one request to the backend and return its JSON, or raise Refused."""
    response = backend.request(method, path, **request)
    if response.is_error:
        raise Refused(f"{response.status_code}: {response.json()['detail']}")
    return response.json()


def list_claims() -> list[dict[str, Any]]:
    return _call("GET", "/claims")


def get_claim(claim_id: str) -> dict[str, Any]:
    return _call("GET", f"/claims/{claim_id}")


def get_policy(policy_id: str) -> dict[str, Any]:
    return _call("GET", f"/policies/{policy_id}")


def get_claim_history(customer_id: str) -> list[dict[str, Any]]:
    return _call("GET", f"/customers/{customer_id}/claims")


def get_instructions() -> dict[str, str]:
    return _call("GET", "/instructions")


def search_documents(query: str) -> list[dict[str, Any]]:
    return _call("GET", "/documents/search", params={"query": query})


def read_section(document: DocumentName, number: int) -> dict[str, Any]:
    return _call("GET", f"/documents/{document}/sections/{number}")


def start_claim(claim_id: str, thread_id: str) -> dict[str, Any]:
    return _call("POST", f"/claims/{claim_id}/start", json={"thread_id": thread_id})


def record_step(claim_id: str, kind: StepKind, content: str) -> dict[str, Any]:
    body = {"kind": kind, "content": content}
    return _call("POST", f"/claims/{claim_id}/steps", json=body)


def record_decision(
    claim_id: str, decision: DecisionKind, payout: float, section: str, reason: str
) -> dict[str, Any]:
    body = {
        "decision": decision,
        "payout": payout,
        "section": section,
        "reason": reason,
    }
    return _call("POST", f"/claims/{claim_id}/decision", json=body)


def pay_claim(claim_id: str, amount: float) -> dict[str, Any]:
    return _call("POST", f"/claims/{claim_id}/payment", json={"amount": amount})


def fail_claim(claim_id: str, reason: str) -> dict[str, Any]:
    return _call("POST", f"/claims/{claim_id}/failure", json={"reason": reason})


def start_run(cap: int) -> dict[str, Any]:
    return _call("POST", "/runs", json={"cap": cap})


def write_todos(run_id: str, todos: list[Todo]) -> dict[str, Any]:
    return _call("PUT", f"/runs/{run_id}/todos", json={"todos": todos})


def finish_run(run_id: str, summary: str) -> dict[str, Any]:
    return _call("POST", f"/runs/{run_id}/finish", json={"summary": summary})
