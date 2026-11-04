import { getInstructions } from "./api";
import { Markdown } from "./Markdown";
import { useLoad } from "./useLoad";

export function InstructionsPage() {
  const { data, failed } = useLoad(getInstructions, null);

  return (
    <>
      <header className="page-header">
        <div>
          <h1>Agent instructions</h1>
          <p className="muted">
            What the agent is told to do on every claim. You can read them here
            but not change them.
          </p>
        </div>
      </header>
      {failed && (
        <p className="panel error" role="alert">
          We could not load the instructions. Try again.
        </p>
      )}
      {data !== undefined && (
        <section className="panel">
          <Markdown source={data} />
        </section>
      )}
    </>
  );
}
