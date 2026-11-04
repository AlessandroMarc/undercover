import { getQueue } from "./api";
import { formatCount, formatMoney, humanize } from "./format";
import { StatusBadge } from "./StatusBadge";
import type { ClaimSummary, Status } from "./types";
import { useLoad } from "./useLoad";

const REFRESH_MS = 3000;
const STATES: { status: Status; label: string }[] = [
  { status: "waiting", label: "Waiting" },
  { status: "in_progress", label: "In progress" },
  { status: "awaiting_signoff", label: "Needs sign-off" },
  { status: "decided", label: "Decided" },
];

function Counts({ claims }: Readonly<{ claims: ClaimSummary[] }>) {
  return (
    <section className="panel counts" aria-label="Queue summary">
      {STATES.map(({ status, label }) => (
        <div className="nested" key={status}>
          <span className="label">{label}</span>
          <span className="figure">
            {claims.filter((claim) => claim.status === status).length}
          </span>
        </div>
      ))}
    </section>
  );
}

function Row({ claim }: Readonly<{ claim: ClaimSummary }>) {
  return (
    <tr>
      <td className="mono">
        <a href={`#/claims/${claim.claim_id}`}>{claim.claim_id}</a>
      </td>
      <td>{claim.customer_name}</td>
      <td>{humanize(claim.claim_type)}</td>
      <td className="num">{formatMoney(claim.amount_claimed)}</td>
      <td className="num">
        {claim.payout === null ? "—" : formatMoney(claim.payout)}
      </td>
      <td>
        <StatusBadge status={claim.status} decision={claim.decision} />
      </td>
    </tr>
  );
}

export function QueuePage() {
  const { data, failed } = useLoad(getQueue, REFRESH_MS);

  return (
    <>
      <header className="page-header">
        <div>
          <h1>Claims</h1>
          <p className="accent">Here is where your claims stand today.</p>
        </div>
        {data && <p className="count">{formatCount(data.length, "claim")}</p>}
      </header>
      {failed && (
        <p className="panel error" role="alert">
          We could not load the claims. Check that the backend is running and
          try again.
        </p>
      )}
      {data && (
        <>
          <Counts claims={data} />
          <section className="panel">
            <table>
              <thead>
                <tr>
                  <th>Claim</th>
                  <th>Customer</th>
                  <th>Type</th>
                  <th className="num">Claimed</th>
                  <th className="num">Payout</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {data.map((claim) => (
                  <Row key={claim.claim_id} claim={claim} />
                ))}
              </tbody>
            </table>
          </section>
        </>
      )}
      {!data && !failed && <p className="muted">Loading claims</p>}
    </>
  );
}
