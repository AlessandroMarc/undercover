import type { DecisionKind, Status } from "../api";
import { decisionLabels, statusLabels } from "../format";

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
