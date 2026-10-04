import { useState } from "react";
import { api, type Improvement, type RoundView } from "../api";
import { ActionForm } from "../components/ActionForm";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { NotAllowed } from "../components/NotAllowed";
import { PageHeader } from "../components/PageHeader";
import { ProposalPanel } from "../components/ProposalPanel";
import { Recipes } from "../components/Recipes";
import { RoundPanel } from "../components/RoundPanel";
import { Rounds } from "../components/Rounds";
import { StateMessage } from "../components/StateMessage";
import { VersionChart } from "../components/VersionChart";
import { useHandler } from "../handler";
import { useAction } from "../useAction";
import { REFRESH_MS, useLoad } from "../useLoad";

export function ImprovementPage() {
  const { data: page, error, reload } = useLoad(api.getImprovement, REFRESH_MS);
  // A review's refusal, kept here so it stays on screen when the proposal it
  // was for is no longer waiting.
  const [refusal, setRefusal] = useState<string>();
  const open = page?.round?.status === "open" ? page.round : undefined;
  const header = (
    <PageHeader
      title="Improvement"
      lead="Rounds of the improver, which proposes changes to the claim agent for a handler to approve, and keeps each version only if the business's rule does."
      action={page && <RoundAction open={open} onDone={reload} />}
    />
  );
  if (!page)
    return (
      <>
        {header}
        <StateMessage error={error} />
      </>
    );
  return (
    <>
      {header}
      <div className="column">
        {page.round && <RoundPanel round={page.round} />}
        {refusal && (
          <p className="form-error" role="alert">
            {refusal}
          </p>
        )}
        {page.round?.waiting && (
          <ProposalPanel
            round={page.round}
            proposal={page.round.waiting}
            onReviewed={() => {
              setRefusal(undefined);
              reload();
            }}
            onRefused={setRefusal}
          />
        )}
        <VersionsTried page={page} />
        <Rounds rounds={page.rounds} />
        <Recipes recipes={page.recipes} />
      </div>
    </>
  );
}

// Start a round, or Stop the round while one is open, for a handler who can
// sign off over the limit; for anyone else, what they can't do and why.
function RoundAction({
  open,
  onDone,
}: Readonly<{ open?: RoundView; onDone: () => void }>) {
  const handler = useHandler();
  if (!handler.can_approve_over_limit)
    return <NotAllowed action={open ? "stop a round" : "start a round"} />;
  if (open)
    return <StopRound key={open.round_id} round={open} onStopped={onDone} />;
  return (
    <ActionForm
      label="Start a round"
      action={() => api.startRound().then(onDone)}
    />
  );
}

function StopRound({
  round,
  onStopped,
}: Readonly<{ round: RoundView; onStopped: () => void }>) {
  const [confirming, setConfirming] = useState(false);
  const stop = useAction(() => api.stopRound(round.round_id).then(onStopped));
  return (
    <div className="action-form">
      <button
        type="button"
        className="button quiet"
        aria-disabled={stop.sending}
        onClick={() => {
          setConfirming(true);
        }}
      >
        Stop the round
      </button>
      {stop.error && (
        <p className="form-error" role="alert">
          {stop.error}
        </p>
      )}
      <ConfirmDialog
        open={confirming}
        title={`Stop round ${String(round.number)}?`}
        confirmLabel="Stop the round"
        onConfirm={() => {
          setConfirming(false);
          stop.run();
        }}
        onCancel={() => {
          setConfirming(false);
        }}
      >
        <p>
          No more of its claims start and the improver stops. A version under
          test is rolled back, and the current version stays as it is.
        </p>
      </ConfirmDialog>
    </div>
  );
}

function VersionsTried({ page }: Readonly<{ page: Improvement }>) {
  return (
    <section className="panel" aria-labelledby="tried-title">
      <h2 id="tried-title">Versions tried</h2>
      {page.versions_tried.length === 0 ? (
        <StateMessage empty="No version tried yet. Each version a round tries shows here with its held-out accuracy and grade." />
      ) : (
        <VersionChart first={page.first_version} tried={page.versions_tried} />
      )}
    </section>
  );
}
