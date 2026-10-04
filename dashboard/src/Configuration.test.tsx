import { cleanup, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { Configuration, VersionDetails, VersionSummary } from "./api";
import { renderAt, stubApi } from "./testing";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const first: VersionSummary = {
  number: 1,
  status: "kept",
  model: "openai/gpt-6-luna",
  reasoning_effort: "low",
  model_before: null,
  reasoning_effort_before: null,
  based_on: null,
  lines_added: 0,
  lines_removed: 0,
  reason: "The claim agent as the claims team built it",
  proposed_by: "The claims team",
  round_id: null,
  approved_by: null,
  approved_at: null,
  created_at: "2026-10-04T09:00:00+00:00",
  verdict: "kept",
  verdict_reason: "the first version",
  scores: { evaluation: null, held_out: null },
};

const second: VersionSummary = {
  ...first,
  number: 2,
  status: "current",
  model: "google/gemini-3.5-flash-lite",
  reasoning_effort: "minimal",
  model_before: "openai/gpt-6-luna",
  reasoning_effort_before: "low",
  based_on: 1,
  lines_added: 12,
  lines_removed: 3,
  reason: "Add a rule for stolen phones",
  proposed_by: "Round 1",
  approved_by: "Dana Whitfield",
  approved_at: "2026-10-05T14:05:00+00:00",
};

const configuration: Configuration = { current: 2, versions: [second, first] };

it("shows the current version and every version with its status", async () => {
  stubApi({ "GET /api/configuration": configuration });
  renderAt("/configuration");
  const current = within(
    await screen.findByRole("region", { name: "Current version" }),
  );
  expect(current.getByText("google/gemini-3.5-flash-lite")).toBeDefined();
  expect(current.getByText("Minimal")).toBeDefined();
  expect(current.getByText("Not scored yet")).toBeDefined();

  const rows = within(
    screen.getByRole("region", { name: "Versions" }),
  ).getAllByRole("row");
  const two = within(rows[1]);
  expect(two.getByText("Current").className).toBe("chip version-current");
  expect(rows[1].textContent).toContain("+12 −3 lines");
  expect(rows[1].textContent).toContain(
    "openai/gpt-6-luna at low to google/gemini-3.5-flash-lite at minimal",
  );
  expect(two.getByText("Dana Whitfield")).toBeDefined();
  expect(within(rows[2]).getByText("Kept")).toBeDefined();
  expect(rows[2].textContent).toContain("The first version");
  expect(
    within(rows[2]).getByRole("link", { name: "1" }).getAttribute("href"),
  ).toBe("/configuration/versions/1");
});

it("marks the Configuration page in the header", async () => {
  stubApi({ "GET /api/configuration": configuration });
  renderAt("/configuration");
  const nav = within(await screen.findByRole("navigation", { name: "Main" }));
  expect(
    nav
      .getByRole("link", { name: "Configuration" })
      .getAttribute("aria-current"),
  ).toBe("page");
});

it("sends the old Instructions page to the Configuration page", async () => {
  stubApi({ "GET /api/configuration": configuration });
  renderAt("/instructions");
  expect(
    await screen.findByRole("heading", { name: "Configuration", level: 1 }),
  ).toBeDefined();
});

const details: VersionDetails = {
  ...second,
  instructions: "# Working a claim\n\n## Contents of the claims manual",
  diff: {
    added: 1,
    removed: 1,
    hunks: [
      [
        { kind: "context", text: "Read the claim." },
        { kind: "removed", text: "Refer a stolen phone." },
        { kind: "added", text: "Decline a phone left unattended." },
      ],
      [{ kind: "context", text: "Record the decision." }],
    ],
  },
};

it("shows a version's diff and its instructions, read only", async () => {
  stubApi({ "GET /api/configuration/versions/2": details });
  renderAt("/configuration/versions/2");
  const changes = within(
    await screen.findByRole("region", {
      name: "What changed from version 1",
    }),
  );
  expect(changes.getByText("Refer a stolen phone.").tagName).toBe("DEL");
  expect(changes.getByText("Decline a phone left unattended.").tagName).toBe(
    "INS",
  );
  expect(changes.getByText("Read the claim.").tagName).toBe("SPAN");
  expect(document.querySelectorAll(".diff-gap")).toHaveLength(1);
  const instructions = within(
    screen.getByRole("region", { name: "Instructions" }),
  );
  expect(
    instructions.getByText(/## Contents of the claims manual/),
  ).toBeDefined();
  expect(screen.queryByRole("textbox")).toBeNull();
});

it("says version 1 has nothing before it", async () => {
  stubApi({
    "GET /api/configuration/versions/1": { ...details, ...first, diff: null },
  });
  renderAt("/configuration/versions/1");
  expect(await screen.findByText(/nothing before it to compare/)).toBeDefined();
});

it("says when a version doesn't exist", async () => {
  stubApi({});
  renderAt("/configuration/versions/9");
  expect(await screen.findByText("Version not found")).toBeDefined();
});
