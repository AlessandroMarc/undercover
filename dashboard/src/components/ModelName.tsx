import type { RunDetails } from "../api";

export function ModelName({
  run,
}: Readonly<{ run: Pick<RunDetails, "model" | "reasoning_effort"> }>) {
  return (
    <>
      <span className="mono">{run.model}</span>, reasoning effort{" "}
      {run.reasoning_effort}
    </>
  );
}
