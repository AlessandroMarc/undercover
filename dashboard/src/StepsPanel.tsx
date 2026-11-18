import { formatDateTime, formatRelative } from "./format";
import type { Step, StepKind } from "./types";

const KINDS: Record<StepKind, string> = {
  tool_call: "Tool call",
  tool_result: "Result",
  message: "Agent",
  read: "Read",
};

export function SectionsPanel({ steps }: Readonly<{ steps: Step[] }>) {
  const reads = [
    ...new Set(steps.filter((step) => step.kind === "read").map((s) => s.text)),
  ];
  return (
    <section className="panel stack">
      <h2>Sections read</h2>
      {reads.length === 0 ? (
        <p className="muted">
          None yet. The sections of the policy wording and the claims manual
          that the agent reads appear here.
        </p>
      ) : (
        <ul className="steps">
          {reads.map((text) => (
            <li className="nested" key={text}>
              {text}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export function StepsPanel({ steps }: Readonly<{ steps: Step[] }>) {
  const now = new Date();
  return (
    <section className="panel stack">
      <h2>Agent steps</h2>
      {steps.length === 0 ? (
        <p className="muted">
          No steps yet. They appear here when the agent starts on this claim.
        </p>
      ) : (
        <ol className="steps">
          {steps.map((step) => (
            <li className="nested" key={step.id}>
              <div className="row between">
                <span className="label">{KINDS[step.kind]}</span>
                <time
                  className="mono small"
                  dateTime={step.created_at}
                  title={formatDateTime(step.created_at)}
                >
                  {formatRelative(step.created_at, now)}
                </time>
              </div>
              <p className={step.kind === "message" ? undefined : "code"}>
                {step.text}
              </p>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
