import type { DecisionKind, RunStatus, Status } from "../api";
import { decisionLabels, money, runLabels, statusLabels } from "../format";

export function StatusChip({ status }: Readonly<{ status: Status }>) {
  return (
    <span className={`chip status-${status}`}>{statusLabels[status]}</span>
  );
}

export function DecisionChip({
  decision,
}: Readonly<{ decision: DecisionKind }>) {
  return (
    <span className={`chip decision-${decision}`}>
      {decisionLabels[decision]}
    </span>
  );
}

export function RunChip({ status }: Readonly<{ status: RunStatus }>) {
  return <span className={`chip run-${status}`}>{runLabels[status]}</span>;
}

// Whether the agent's decision and payout match the handler's.
export function RightChip({ right }: Readonly<{ right: boolean }>) {
  return right ? (
    <span className="chip score-right">Right</span>
  ) : (
    <span className="chip score-miss">Miss</span>
  );
}

export function DecisionPayout({
  decision,
  payout,
}: Readonly<{ decision: DecisionKind; payout: number }>) {
  return (
    <>
      <DecisionChip decision={decision} />{" "}
      <span className="mono">{money(payout)}</span>
    </>
  );
}
