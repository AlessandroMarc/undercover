import type { DecisionKind, RunStatus, Status, TodoStatus } from "../api";
import { decisionLabels, runLabels, statusLabels, todoLabels } from "../format";

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

export function TodoChip({ status }: Readonly<{ status: TodoStatus }>) {
  return <span className={`chip todo-${status}`}>{todoLabels[status]}</span>;
}

export function RunChip({ status }: Readonly<{ status: RunStatus }>) {
  return <span className={`chip run-${status}`}>{runLabels[status]}</span>;
}
