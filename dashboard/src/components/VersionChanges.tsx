import type { VersionSummary } from "../api";
import { ModelName } from "./ModelName";

// What a version changed from the one it was based on: lines of its
// instructions, and its model or reasoning effort.
export function VersionChanges({
  version,
}: Readonly<{ version: VersionSummary }>) {
  const { model_before, reasoning_effort_before } = version;
  if (model_before === null || reasoning_effort_before === null)
    return <>The first version</>;
  const modelChanged =
    version.model !== model_before ||
    version.reasoning_effort !== reasoning_effort_before;
  return (
    <>
      <span className="mono nowrap">
        <span className="diff-added-count">+{version.lines_added}</span>{" "}
        <span className="diff-removed-count">−{version.lines_removed}</span>
      </span>{" "}
      lines
      {modelChanged && (
        <>
          ,{" "}
          <ModelName
            model={model_before}
            reasoningEffort={reasoning_effort_before}
          />{" "}
          to{" "}
          <ModelName
            model={version.model}
            reasoningEffort={version.reasoning_effort}
          />
        </>
      )}
    </>
  );
}
