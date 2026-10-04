import type { VersionScores } from "../api";
import { percent } from "../format";

// A version's accuracy on the held-out set, once rounds have scored it.
export function HeldOutAccuracy({
  scores,
}: Readonly<{ scores: VersionScores }>) {
  return scores.held_out ? (
    <span className="mono">{percent(scores.held_out.accuracy)}</span>
  ) : (
    <span className="muted">Not scored yet</span>
  );
}
