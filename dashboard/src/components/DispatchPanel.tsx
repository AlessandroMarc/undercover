import { Fragment } from "react";
import { Link } from "react-router";
import { api, type DispatchSummary, type Run, type RunClaim } from "../api";
import { duration, modelCost, money, time } from "../format";
import { claimPage } from "../paths";
import { REFRESH_MS, useLoad } from "../useLoad";
import { DecisionChip, RunChip, StatusChip } from "./Chips";
import { Message } from "./Message";

export function DispatchPanel() {
  const { data: dispatch, error } = useLoad(api.getLatestDispatch, REFRESH_MS);

  return (
    <section className="panel run" aria-labelledby="dispatch-title">
      <div className="run-heading">
        <h2 id="dispatch-title">Dispatch</h2>
        {dispatch && <RunChip status={dispatch.status} />}
      </div>
      {dispatch === undefined && <Message error={error} />}
      {dispatch === null && <p className="muted">No dispatch yet.</p>}
      {dispatch && <DispatchDetails dispatch={dispatch} />}
    </section>
  );
}

function DispatchDetails({ dispatch }: Readonly<{ dispatch: Run }>) {
  const agents = `${String(dispatch.agents)} claim ${dispatch.agents === 1 ? "agent" : "agents"}`;
  return (
    <>
      <p className="muted small">
        <span className="mono">#{dispatch.number}</span> started at{" "}
        {time(dispatch.started_at)} with {agents} at once. Model cost{" "}
        <span className="mono">{modelCost(dispatch.model_cost)}</span>
        {dispatch.seconds !== null && (
          <>
            , took <span className="mono">{duration(dispatch.seconds)}</span>
          </>
        )}
        .
      </p>
      {dispatch.status === "stopped" && (
        <p className="stopped">
          It stopped before it finished. The next dispatch carries on its
          claims.
        </p>
      )}
      {dispatch.claims.length > 0 ? (
        <RunClaims claims={dispatch.claims} />
      ) : (
        <p className="muted">No claims in this dispatch.</p>
      )}
      {dispatch.summary && <Summary summary={dispatch.summary} />}
    </>
  );
}

function RunClaims({ claims }: Readonly<{ claims: RunClaim[] }>) {
  return (
    <div className="table-scroll">
      <table className="table">
        <thead>
          <tr>
            <th>Claim</th>
            <th>Customer</th>
            <th>State</th>
            <th>Decision</th>
            <th className="num">Payout</th>
            <th className="num">Time</th>
            <th className="num">Model cost</th>
          </tr>
        </thead>
        <tbody>
          {claims.map((claim) => (
            <tr key={claim.claim_id}>
              <td className="nowrap">
                <Link className="mono" to={claimPage(claim.claim_id)}>
                  {claim.claim_id}
                </Link>
              </td>
              <td>{claim.customer_name}</td>
              <td>
                <StatusChip status={claim.status} />
              </td>
              <td>
                {claim.decision && <DecisionChip decision={claim.decision} />}
              </td>
              <td className="num mono">
                {claim.payout !== null && money(claim.payout)}
              </td>
              <td className="num mono">{duration(claim.seconds)}</td>
              <td className="num mono">{modelCost(claim.model_cost)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Summary({ summary }: Readonly<{ summary: DispatchSummary }>) {
  const held = summary.waiting_for_sign_off.map(({ claim_id, payout }) => ({
    claim_id,
    note: money(payout),
  }));
  const only = (ids: string[]) => ids.map((claim_id) => ({ claim_id }));
  return (
    <div className="dispatch-summary">
      <h3 id="dispatch-summary-title">Summary</h3>
      <ul aria-labelledby="dispatch-summary-title">
        <li>
          {summary.approved} approved, {summary.declined} declined and{" "}
          {summary.referred} referred.
        </li>
        <ClaimLine label="Waiting for sign-off" claims={held} />
        <ClaimLine
          label="Left for a handler"
          claims={only(summary.left_for_handler)}
        />
        <ClaimLine
          label="Left for the next dispatch"
          claims={only(summary.unfinished)}
        />
      </ul>
    </div>
  );
}

function ClaimLine({
  label,
  claims,
}: Readonly<{ label: string; claims: { claim_id: string; note?: string }[] }>) {
  if (claims.length === 0) return null;
  return (
    <li>
      {label}:{" "}
      {claims.map(({ claim_id, note }, index) => (
        <Fragment key={claim_id}>
          {index > 0 && ", "}
          <Link className="mono" to={claimPage(claim_id)}>
            {claim_id}
          </Link>
          {note && <span className="mono"> {note}</span>}
        </Fragment>
      ))}
    </li>
  );
}
