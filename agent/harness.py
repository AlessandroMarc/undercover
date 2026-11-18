"""Work one claim with the claim agent, and put right what goes wrong."""

from uuid import uuid4

from langchain_core.language_models import BaseChatModel

from agent import main as core
from agent.main import ClaimError, run

MAX_REASON_CHARS = 100


def money(amount: float) -> str:
    return f"${amount:,.2f}"


def work_claim(claim_id: str, llm: BaseChatModel | None = None) -> str:
    """Run the claim agent on one claim and return a one-line report.

    A claim with no decision afterwards goes back in the queue, or to a handler on
    its second failure. A claim that was decided is never run again.
    """
    reason = "the agent finished without a decision"
    try:
        run(claim_id, f"{claim_id}-{uuid4().hex[:8]}", llm)
    except ClaimError:
        raise
    except Exception as error:  # one bad claim must not stop the run
        reason = f"{type(error).__name__}: {error}"[:MAX_REASON_CHARS]
    with core.backend() as client:
        claim = client.get(f"/api/claims/{claim_id}").json()
        if claim["decision"] is None:
            failed = client.post(
                f"/api/claims/{claim_id}/failure", json={"reason": reason}
            ).json()
            if failed["status"] == "needs_handler":
                return f"{claim_id}: failed twice ({reason}), left for a handler"
            return f"{claim_id}: failed ({reason}), back in the queue"
        decision = claim["decision"]
        if (
            decision["decision"] == "approve"
            and claim["status"] == "decided"
            and claim["payment"] is None
        ):
            client.post(
                f"/api/claims/{claim_id}/payment", json={"amount": decision["payout"]}
            ).raise_for_status()
            client.post(
                f"/api/claims/{claim_id}/steps",
                json={"kind": "message", "text": "Payment made after the agent's run."},
            ).raise_for_status()
    line = f"{claim_id}: {decision['decision']}"
    if decision["decision"] == "approve":
        line += f", payout {money(decision['payout'])}"
    if claim["status"] == "awaiting_signoff":
        line += ", waiting for sign-off"
    return line
