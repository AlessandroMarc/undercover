import { getPolicyView } from "./api";
import { formatDate, formatMoney, humanize } from "./format";
import type { Claim } from "./types";
import { useLoad } from "./useLoad";

const ADD_ONS: Record<string, string> = {
  adventure_sports: "Adventure Sports",
  pre_existing_waiver: "Pre-Existing Condition Waiver",
  electronics_plus: "Electronics Plus",
};

function Fact({
  label,
  children,
  figure = false,
}: Readonly<{ label: string; children: string; figure?: boolean }>) {
  return (
    <div className="fact">
      <dt className="label">{label}</dt>
      <dd className={figure ? "mono" : undefined}>{children}</dd>
    </div>
  );
}

export function ClaimPanel({ claim }: Readonly<{ claim: Claim }>) {
  return (
    <section className="panel">
      <h2>Claim</h2>
      <dl className="facts">
        <Fact label="Type">{humanize(claim.claim_type)}</Fact>
        <Fact label="Incident date" figure>
          {formatDate(claim.incident_date)}
        </Fact>
        <Fact label="Location">{claim.incident_location}</Fact>
        <Fact label="Submitted" figure>
          {formatDate(claim.submitted_on)}
        </Fact>
        <Fact label="Claimed" figure>
          {formatMoney(claim.amount_claimed)}
        </Fact>
      </dl>
      <h3>Customer's story</h3>
      <p>{claim.story}</p>
      <h3>Items claimed</h3>
      <table>
        <thead>
          <tr>
            <th>Item</th>
            <th>Category</th>
            <th className="num">Amount</th>
          </tr>
        </thead>
        <tbody>
          {claim.items.map((item) => (
            <tr key={item.description}>
              <td>{item.description}</td>
              <td>{humanize(item.category)}</td>
              <td className="num">{formatMoney(item.amount)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <h3>Documents</h3>
      <div className="stack">
        {claim.documents.map((document) => (
          <article className="nested" key={document.name}>
            <h4>{document.name}</h4>
            <p className="muted">{humanize(document.type)}</p>
            <p>{document.content}</p>
          </article>
        ))}
      </div>
    </section>
  );
}

export function PolicyPanel({ claim }: Readonly<{ claim: Claim }>) {
  const { data, failed } = useLoad(
    () => getPolicyView(claim.policy_id, claim.customer_id),
    null,
  );

  return (
    <section className="panel">
      <h2>Policy and customer</h2>
      {failed && (
        <p className="error" role="alert">
          We could not load the policy. Reload the page to try again.
        </p>
      )}
      {data && (
        <>
          <dl className="facts">
            <Fact label="Policy" figure>
              {data.policy.policy_id}
            </Fact>
            <Fact label="Plan">{humanize(data.policy.plan)}</Fact>
            <Fact label="Add-ons">
              {data.policy.add_ons.length > 0
                ? data.policy.add_ons
                    .map((addOn) => ADD_ONS[addOn] ?? humanize(addOn))
                    .join(", ")
                : "None"}
            </Fact>
            <Fact label="Purchased" figure>
              {formatDate(data.policy.purchased_on)}
            </Fact>
            <Fact label="Trip">{data.policy.trip.destination}</Fact>
            <Fact label="Departs" figure>
              {formatDate(data.policy.trip.departs_on)}
            </Fact>
            <Fact label="Returns" figure>
              {formatDate(data.policy.trip.returns_on)}
            </Fact>
            <Fact label="Trip cost" figure>
              {formatMoney(data.policy.trip.trip_cost)}
            </Fact>
            <Fact label="Travelers">{data.policy.travelers.join(", ")}</Fact>
            <Fact label="Customer">{data.customer.name}</Fact>
            <Fact label="Customer since" figure>
              {formatDate(data.customer.customer_since)}
            </Fact>
          </dl>
          <h3>Claim history</h3>
          {data.customer.previous_claims.length === 0 ? (
            <p className="muted">No earlier claims.</p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Claim</th>
                  <th>Filed</th>
                  <th>Summary</th>
                  <th>Outcome</th>
                  <th className="num">Paid</th>
                </tr>
              </thead>
              <tbody>
                {data.customer.previous_claims.map((previous) => (
                  <tr key={previous.claim_id}>
                    <td className="mono">{previous.claim_id}</td>
                    <td className="mono">{formatDate(previous.filed_on)}</td>
                    <td>{previous.summary}</td>
                    <td>{humanize(previous.outcome)}</td>
                    <td className="num">{formatMoney(previous.amount_paid)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </section>
  );
}
