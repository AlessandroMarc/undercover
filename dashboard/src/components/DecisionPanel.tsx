import type { Claim } from "../api";
import { money, time } from "../format";
import { DecisionChip } from "./Chips";
import { SignOffForm } from "./SignOffForm";

function progress(claim: Claim): string {
  if (claim.status === "in_progress")
    return "The agent is working on this claim.";
  if (claim.status === "left_for_handler")
    return `The agent couldn't finish this claim in ${String(claim.attempts)} attempts, so it's left for a handler.`;
  if (claim.attempts > 0) return "Back in the queue after a failed attempt.";
  return "The agent hasn't started on this claim.";
}

export function DecisionPanel({
  claim,
  onSignedOff,
}: Readonly<{ claim: Claim; onSignedOff: () => void }>) {
  const { decision, payment } = claim;

  return (
    <section className="panel" aria-labelledby="decision-title">
      <h2 id="decision-title">Decision</h2>
      {!decision && <p className="muted">{progress(claim)}</p>}
      {decision && (
        <>
          <div className="decision-line">
            <DecisionChip decision={decision.decision} />
            {decision.decision === "approve" && (
              <span className="payout mono">{money(decision.payout)}</span>
            )}
          </div>
          <p className="section-ref">{decision.section}</p>
          <p className="reason">{decision.reason}</p>
          <p className="small muted">Decided at {time(decision.decided_at)}</p>
        </>
      )}
      {payment && (
        <p className="payment">
          Paid <span className="mono">{money(payment.amount)}</span>
          {payment.signed_off_by && `, signed off by ${payment.signed_off_by}`}
        </p>
      )}
      {decision?.decision === "approve" &&
        !payment &&
        claim.status === "decided" && <p className="payment">Not paid yet</p>}
      {decision && claim.status === "waiting_for_sign_off" && (
        <div className="sign-off">
          <p>
            The payment of{" "}
            <span className="mono">{money(decision.payout)}</span> is over the
            approval limit and waits for a handler's sign-off.
          </p>
          <SignOffForm claimId={claim.claim_id} onSignedOff={onSignedOff} />
        </div>
      )}
    </section>
  );
}
