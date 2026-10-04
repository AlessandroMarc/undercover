import { useCallback } from "react";
import { useParams } from "react-router";
import { api, type ScoredClaim, type ScoredEvaluation } from "../api";
import { DecisionPayout, RightChip, RunChip } from "../components/Chips";
import { ClaimLink } from "../components/ClaimLink";
import { StateMessage } from "../components/StateMessage";
import { ModelName } from "../components/ModelName";
import {
  agentsAtOnce,
  dateTime,
  duration,
  evaluationSetName,
  modelCost,
  money,
} from "../format";
import { MEASURES } from "../measures";
import { REFRESH_MS, useLoad } from "../useLoad";

export function EvaluationPage() {
  const { runId = "" } = useParams();
  const load = useCallback(() => api.getEvaluation(runId), [runId]);
  const { data: evaluation, error } = useLoad(load, REFRESH_MS);

  if (!evaluation)
    return <StateMessage error={error} notFound="Evaluation not found" />;

  return (
    <>
      <div className="title-row">
        <h1>Evaluation #{evaluation.number}</h1>
        <RunChip status={evaluation.status} />
      </div>
      <div className="column">
        <MeasuresPanel evaluation={evaluation} />
        <ScoredClaims claims={evaluation.claims} />
      </div>
    </>
  );
}

function MeasuresPanel({
  evaluation,
}: Readonly<{ evaluation: ScoredEvaluation }>) {
  return (
    <section className="panel" aria-labelledby="measures-title">
      <h2 id="measures-title">Measures</h2>
      <p className="muted small">
        {evaluationSetName(evaluation.evaluation_set, evaluation.size)}, with{" "}
        {agentsAtOnce(evaluation.agents)} on{" "}
        <ModelName
          model={evaluation.model}
          reasoningEffort={evaluation.reasoning_effort}
        />
        . Started {dateTime(evaluation.started_at)}.
      </p>
      <dl className="facts measures">
        {MEASURES.map(({ label, show }) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd className="mono">{show(evaluation.measures)}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

function ScoredClaims({ claims }: Readonly<{ claims: ScoredClaim[] }>) {
  return (
    <section className="panel" aria-labelledby="claims-title">
      <h2 id="claims-title">Claims</h2>
      <p className="muted small">
        A claim the agent didn't decide counts as a referral.
      </p>
      <div className="table-scroll">
        <table className="table">
          <thead>
            <tr>
              <th>Copy</th>
              <th>Of</th>
              <th>Handler</th>
              <th>Agent</th>
              <th>Score</th>
              <th className="num">Mistake cost</th>
              <th className="num">Model cost</th>
              <th className="num">Time</th>
              <th>The agent's reason</th>
            </tr>
          </thead>
          <tbody>
            {claims.map((claim) => (
              <tr key={claim.claim_id}>
                <td className="nowrap">
                  <ClaimLink claimId={claim.claim_id} />
                </td>
                <td className="mono nowrap">{claim.copy_of}</td>
                <td className="nowrap">
                  <DecisionPayout
                    decision={claim.handler_decision}
                    payout={claim.handler_payout}
                  />
                </td>
                <td className="nowrap">
                  {claim.decision && claim.payout !== null ? (
                    <DecisionPayout
                      decision={claim.decision}
                      payout={claim.payout}
                    />
                  ) : (
                    <span className="muted">No decision</span>
                  )}
                </td>
                <td>
                  <RightChip right={claim.right} />
                </td>
                <td className="num mono">{money(claim.mistake_cost)}</td>
                <td className="num mono">{modelCost(claim.model_cost)}</td>
                <td className="num mono">{duration(claim.seconds)}</td>
                <td className="small">{claim.reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
