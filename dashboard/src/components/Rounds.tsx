import { Link } from "react-router";
import type { Measures, RoundReview, RoundSummary } from "../api";
import {
  dateTime,
  grade,
  modelCost,
  money,
  percent,
  whereRoundIs,
} from "../format";
import { NOT_GRADED } from "../measures";
import { recipePage, versionPage } from "../paths";
import { RoundChip, VerdictChip } from "./Chips";

// Every round, newest first: what it tried and why, the held-out scores before
// and after, its verdict and why, who approved or rejected what and when, and
// what it cost against its limit.
export function Rounds({ rounds }: Readonly<{ rounds: RoundSummary[] }>) {
  return (
    <section className="panel" aria-labelledby="rounds-title">
      <h2 id="rounds-title">Rounds</h2>
      {rounds.length === 0 ? (
        <p className="muted">
          No rounds yet. Starting a round has the improver read the latest
          results and propose a change to the claim agent for a handler to
          approve.
        </p>
      ) : (
        <div className="table-scroll">
          <table className="table rounds">
            <thead>
              <tr>
                <th>Round</th>
                <th>Recipe</th>
                <th>Version tried</th>
                <th>Reason</th>
                <th className="num">Held-out accuracy</th>
                <th className="num">Held-out grade</th>
                <th>Verdict</th>
                <th>Reviews</th>
                <th className="num">Cost</th>
              </tr>
            </thead>
            <tbody>
              {rounds.map((round) => (
                <RoundRow key={round.round_id} round={round} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function RoundRow({ round }: Readonly<{ round: RoundSummary }>) {
  return (
    <tr>
      <td>
        <span className="nowrap">
          <span className="mono">{round.number}</span>{" "}
          <RoundChip status={round.status} />
        </span>
        {round.status === "open" && (
          <span className="round-stage small">{whereRoundIs(round)}</span>
        )}
      </td>
      <td className="mono">
        <Link to={recipePage(round.recipe)}>{round.recipe}</Link>
      </td>
      {round.version === null ? (
        <td className="muted">None</td>
      ) : (
        <td className="mono">
          <Link to={versionPage(round.version)}>{round.version}</Link>
        </td>
      )}
      <td className="round-reason">
        {round.reason ?? <span className="muted">No change</span>}
      </td>
      <td className="num nowrap">
        <BeforeAfter
          round={round}
          show={(measures) => percent(measures.accuracy)}
        />
      </td>
      <td className="num nowrap">
        <BeforeAfter
          round={round}
          show={(measures) =>
            measures.grade === null ? NOT_GRADED : grade(measures.grade)
          }
        />
      </td>
      <td>
        {round.verdict ? (
          <>
            <VerdictChip verdict={round.verdict} />{" "}
            <span className="small">{round.verdict_reason}</span>
          </>
        ) : (
          <span className="muted">{round.stopped_because ?? "None"}</span>
        )}
      </td>
      <td>
        <Reviews reviews={round.reviews} />
      </td>
      <td className="num nowrap">
        {modelCost(round.cost)} of {money(round.spending_limit)}
      </td>
    </tr>
  );
}

// A held-out score before the round's version and after it, each side shown
// on its own, since a version the round couldn't afford to evaluate has no
// score after.
function BeforeAfter({
  round,
  show,
}: Readonly<{ round: RoundSummary; show: (measures: Measures) => string }>) {
  const { held_out_before: before, held_out_after: after } = round;
  if (!before && !after) return <span className="muted">None</span>;
  return (
    <>
      {before ? show(before) : "None"} to {after ? show(after) : "None"}
    </>
  );
}

function Reviews({ reviews }: Readonly<{ reviews: RoundReview[] }>) {
  if (reviews.length === 0) return <span className="muted">None</span>;
  return (
    <ul className="reviews">
      {reviews.map((review) => (
        <li key={review.reviewed_at}>
          {review.reviewed_by} {review.review} the {review.kind},{" "}
          {dateTime(review.reviewed_at)}
          {review.rejection_reason && (
            <span className="muted">: {review.rejection_reason}</span>
          )}
        </li>
      ))}
    </ul>
  );
}
