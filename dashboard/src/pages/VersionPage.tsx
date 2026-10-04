import { useCallback } from "react";
import { Link, useParams } from "react-router";
import { api, type VersionDetails } from "../api";
import { VersionChip } from "../components/Chips";
import { DiffView } from "../components/DiffView";
import { Approval } from "../components/Approval";
import { HeldOutAccuracy, HeldOutGrade } from "../components/HeldOutAccuracy";
import { PageHeader } from "../components/PageHeader";
import { StateMessage } from "../components/StateMessage";
import { VersionChanges } from "../components/VersionChanges";
import { inWords, label } from "../format";
import { CONFIGURATION } from "../paths";
import { REFRESH_MS, useLoad } from "../useLoad";

const LEAD =
  "One version of the claim agent: its instructions, model and reasoning effort, why it was made, and what changed from the version before.";

export function VersionPage() {
  const { number = "" } = useParams();
  const load = useCallback(() => api.getVersionDetails(number), [number]);
  const { data: version, error } = useLoad(load, REFRESH_MS);

  if (!version)
    return (
      <>
        <PageHeader
          eyebrow={<Link to={CONFIGURATION}>Configuration</Link>}
          title={`Version ${number}`}
          lead={LEAD}
        />
        <StateMessage
          error={error}
          notFound="Version not found. Choose one on the Configuration page."
        />
      </>
    );

  return (
    <>
      <PageHeader
        eyebrow={<Link to={CONFIGURATION}>Configuration</Link>}
        title={`Version ${String(version.number)}`}
        status={<VersionChip status={version.status} />}
        lead={LEAD}
      />
      <div className="column">
        <VersionFacts version={version} />
        <section className="panel" aria-labelledby="changes-title">
          <h2 id="changes-title">
            {version.based_on === null
              ? "What changed"
              : `What changed from version ${String(version.based_on)}`}
          </h2>
          {version.diff === null ? (
            <p className="muted">
              This is the first version, so there's nothing before it to
              compare.
            </p>
          ) : (
            <DiffView diff={version.diff} />
          )}
        </section>
        <section className="panel" aria-labelledby="instructions-title">
          <h2 id="instructions-title">Instructions</h2>
          <p className="muted small">
            What each claim agent reads before it starts on a claim, ending with
            the contents of the policy wording and the claims manual. Read only.
          </p>
          <pre className="instructions">{version.instructions}</pre>
        </section>
      </div>
    </>
  );
}

function VersionFacts({ version }: Readonly<{ version: VersionDetails }>) {
  return (
    <section className="panel" aria-labelledby="facts-title">
      <h2 id="facts-title">Details</h2>
      <dl className="facts">
        <div>
          <dt>Model</dt>
          <dd className="mono nowrap">{version.model}</dd>
        </div>
        <div>
          <dt>Reasoning effort</dt>
          <dd>{label(version.reasoning_effort)}</dd>
        </div>
        <div>
          <dt>What changed</dt>
          <dd>
            <VersionChanges version={version} />
          </dd>
        </div>
        <div>
          <dt>Proposed by</dt>
          <dd>{version.proposed_by}</dd>
        </div>
        <div>
          <dt>Approved</dt>
          <dd>
            <Approval by={version.approved_by} at={version.approved_at} />
          </dd>
        </div>
        <div>
          <dt>Held-out accuracy</dt>
          <dd>
            <HeldOutAccuracy scores={version.scores} />
          </dd>
        </div>
        <div>
          <dt>Held-out grade</dt>
          <dd>
            <HeldOutGrade scores={version.scores} />
          </dd>
        </div>
        <div className="fact-wide">
          <dt>Reason</dt>
          <dd>{version.reason}</dd>
        </div>
      </dl>
      {version.diff !== null && version.verdict_reason && (
        <p className="small muted">
          Verdict: {inWords(version.verdict_reason)}
        </p>
      )}
    </section>
  );
}
