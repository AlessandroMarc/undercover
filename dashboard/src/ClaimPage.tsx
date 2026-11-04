import { useCallback } from "react";
import { getClaimView } from "./api";
import { ClaimPanel, PolicyPanel } from "./ClaimDetails";
import { CopyButton } from "./CopyButton";
import { DecisionPanel } from "./DecisionPanel";
import { StepsPanel } from "./StepsPanel";
import { useLoad } from "./useLoad";

const REFRESH_MS = 2000;

export function ClaimPage({ claimId }: Readonly<{ claimId: string }>) {
  const load = useCallback(() => getClaimView(claimId), [claimId]);
  const { data, failed, reload } = useLoad(load, REFRESH_MS);

  return (
    <>
      <header className="page-header">
        <div>
          <a href="#/">Back to claims</a>
          <h1>
            Claim <span className="mono">{claimId}</span>
          </h1>
          {data && <p className="muted">{data.claim.summary}</p>}
        </div>
        <CopyButton text={claimId} />
      </header>
      {failed && !data && (
        <p className="panel error" role="alert">
          We could not load this claim. Check the claim ID and try again.
        </p>
      )}
      {data && (
        <div className="layout">
          <div className="column">
            <DecisionPanel claim={data.claim} onSignedOff={reload} />
            <StepsPanel steps={data.steps} />
          </div>
          <div className="column">
            <ClaimPanel claim={data.claim} />
            <PolicyPanel claim={data.claim} />
          </div>
        </div>
      )}
      {!data && !failed && <p className="muted">Loading claim</p>}
    </>
  );
}
