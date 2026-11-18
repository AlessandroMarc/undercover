import { getLatestRun } from "./api";
import { formatCount, formatDateTime } from "./format";
import { RUNS, TODOS } from "./status";
import { ToneBadge } from "./StatusBadge";
import { useLoad } from "./useLoad";

const REFRESH_MS = 3000;

export function RunPanel() {
  const { data: run } = useLoad(getLatestRun, REFRESH_MS);
  if (run === undefined) return null;
  if (run === null) {
    return (
      <section className="panel stack">
        <h2>Latest run</h2>
        <p className="muted">
          No run yet. Start one with npm run agent and its to-do list appears
          here.
        </p>
      </section>
    );
  }
  const done = run.todos.filter((todo) => todo.status === "done").length;
  const badge = RUNS[run.status];
  return (
    <section className="panel stack">
      <div className="row between">
        <h2>Latest run</h2>
        <ToneBadge {...badge} />
      </div>
      <p className="muted">
        Started {formatDateTime(run.started_at)}, up to{" "}
        {formatCount(run.cap, "claim")}.{" "}
        {run.todos.length > 0 &&
          `${String(done)} of ${String(run.todos.length)} done.`}
      </p>
      {run.todos.length === 0 ? (
        <p className="muted">The agent has not written its to-do list yet.</p>
      ) : (
        <ol className="steps">
          {run.todos.map((todo, index) => (
            <li
              className="nested todo"
              key={`${String(index)}-${todo.content}`}
            >
              <ToneBadge {...TODOS[todo.status]} />
              <span>{todo.content}</span>
            </li>
          ))}
        </ol>
      )}
      {run.summary && (
        <div className="nested stack">
          <span className="label">Summary for the handlers</span>
          <p>{run.summary}</p>
        </div>
      )}
    </section>
  );
}
