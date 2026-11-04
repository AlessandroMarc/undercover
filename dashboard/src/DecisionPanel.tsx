import { useState } from "react";
import { getHandlers, signOff } from "./api";
import { formatDateTime, formatMoney } from "./format";
import { StatusBadge } from "./StatusBadge";
import type { Claim } from "./types";
import { useLoad } from "./useLoad";

const LIMIT_NOTE =
  "This payout is over $1,000.00, so the payment waits for a handler's sign-off.";

function SignOffForm({
  claim,
  onDone,
}: Readonly<{ claim: Claim; onDone: () => void }>) {
  const { data: handlers } = useLoad(getHandlers, null);
  const [handlerId, setHandlerId] = useState("");
  const [failed, setFailed] = useState(false);

  const submit = () => {
    void signOff(claim.claim_id, handlerId).then(onDone, () => {
      setFailed(true);
    });
  };

  return (
    <div className="nested stack">
      <p>{LIMIT_NOTE}</p>
      <div className="row">
        <label className="field">
          <span className="label">Handler</span>
          <select
            value={handlerId}
            onChange={(event) => {
              setHandlerId(event.target.value);
            }}
          >
            <option value="">Choose a handler</option>
            {handlers?.map((handler) => (
              <option key={handler.handler_id} value={handler.handler_id}>
                {handler.name}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          className="button primary"
          disabled={!handlerId}
          onClick={submit}
        >
          Sign off
        </button>
      </div>
      {failed && (
        <p className="error" role="alert">
          We could not record the sign-off. Try again.
        </p>
      )}
    </div>
  );
}

function Outcome({
  claim,
  onSignedOff,
}: Readonly<{
  claim: Claim;
  onSignedOff: () => void;
}>) {
  const { decision, payment, sign_off: signOffRecord } = claim;
  if (!decision) return null;
  return (
    <>
      <div className="outcome">
        <div>
          <span className="label">Payout</span>
          <span className="figure">{formatMoney(decision.payout)}</span>
        </div>
        <div>
          <span className="label">Policy section</span>
          <span>{decision.policy_section}</span>
        </div>
      </div>
      <p>{decision.explanation}</p>
      {claim.status === "awaiting_signoff" && (
        <SignOffForm claim={claim} onDone={onSignedOff} />
      )}
      {signOffRecord && (
        <p className="muted">
          Signed off by {signOffRecord.handler_name} on{" "}
          {formatDateTime(signOffRecord.signed_off_on)}.
        </p>
      )}
      {payment && (
        <p className="muted">
          Paid {formatMoney(payment.amount)} on{" "}
          {formatDateTime(payment.paid_on)}.
        </p>
      )}
      {decision.decision === "approve" &&
        !payment &&
        claim.status === "decided" && <p className="muted">Not paid yet.</p>}
    </>
  );
}

export function DecisionPanel({
  claim,
  onSignedOff,
}: Readonly<{
  claim: Claim;
  onSignedOff: () => void;
}>) {
  return (
    <section className="panel stack">
      <div className="row between">
        <h2>Decision</h2>
        <StatusBadge
          status={claim.status}
          decision={claim.decision?.decision ?? null}
        />
      </div>
      {claim.decision ? (
        <Outcome claim={claim} onSignedOff={onSignedOff} />
      ) : (
        <p className="muted">
          The agent has not decided this claim yet. Its decision appears here.
        </p>
      )}
    </section>
  );
}
