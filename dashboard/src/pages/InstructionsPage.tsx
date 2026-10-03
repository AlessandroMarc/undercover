import { api } from "../api";
import { Message } from "../components/Message";
import { useLoad } from "../useLoad";

export function InstructionsPage() {
  const { data, error } = useLoad(api.getInstructions);

  return (
    <>
      <h1>Agent instructions</h1>
      <p className="lead">
        What each claim agent reads before it starts on a claim, ending with the
        contents of the policy wording and the claims manual. The dispatcher
        that hands out the claims follows fixed rules and has no instructions.
        This page is read only.
      </p>
      <section className="panel" aria-label="Working a claim">
        <h2>Working a claim</h2>
        {data ? (
          <pre className="instructions">{data.claim}</pre>
        ) : (
          <Message error={error} />
        )}
      </section>
    </>
  );
}
