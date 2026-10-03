import { act, cleanup, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { Run, RunClaim } from "./api";
import {
  type Routes,
  summary as claimSummary,
  panel,
  renderAt,
  stubApi,
} from "./testing";
import { REFRESH_MS } from "./useLoad";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

const waiting: RunClaim = {
  ...claimSummary,
  claim_id: "CLM-1013",
  customer_name: "Grace Liu",
  started_at: null,
  seconds: 0,
  model_cost: 0,
};

const running: Run = {
  run_id: "run-4",
  number: 4,
  kind: "dispatch",
  agents: 3,
  model: "openai/gpt-6-luna",
  reasoning_effort: "low",
  evaluation_set: null,
  tiny: null,
  status: "running",
  started_at: "2026-10-03T17:02:13+00:00",
  finished_at: null,
  seconds: null,
  summary: null,
  model_cost: 0.0125,
  claims: [
    {
      ...waiting,
      claim_id: "CLM-1001",
      customer_name: "Maya Patel",
      status: "decided",
      decision: "approve",
      payout: 420,
      started_at: "2026-10-03T17:02:14+00:00",
      seconds: 41,
      model_cost: 0.0125,
    },
    { ...waiting, claim_id: "CLM-1014", status: "in_progress", seconds: 12 },
    waiting,
  ],
};

const finished: Run = {
  ...running,
  status: "finished",
  finished_at: "2026-10-03T17:04:54+00:00",
  seconds: 161,
  claims: running.claims.map((claim) => ({
    ...claim,
    status: "decided",
    decision: "refer",
    payout: 0,
  })),
  summary: {
    approved: 3,
    declined: 1,
    referred: 1,
    waiting_for_sign_off: [
      { claim_id: "CLM-1008", payout: 2240 },
      { claim_id: "CLM-1011", payout: 1150 },
    ],
    left_for_handler: ["CLM-1016"],
    unfinished: ["CLM-1012"],
  },
};

function showQueue(dispatch: Run | null) {
  const routes: Routes = {
    "GET /api/claims": [claimSummary],
    "GET /api/dispatches/latest": dispatch,
  };
  stubApi(routes);
  renderAt("/");
  return routes;
}

const dispatchPanel = () => panel("Dispatch");

it("says when there's no dispatch yet", async () => {
  showQueue(null);
  const panel = await dispatchPanel();
  expect(await panel.findByText("No dispatch yet.")).toBeDefined();
});

it("shows a running dispatch with its claims", async () => {
  showQueue(running);
  const panel = await dispatchPanel();
  expect(await panel.findByText("Running")).toBeDefined();
  expect(panel.getByText(/with 3 claim agents at once/)).toBeDefined();
  expect(panel.getByText("$0.0125", { selector: "p > span" })).toBeDefined();
  expect(panel.queryByText(/took/)).toBeNull();
  const rows = panel.getAllByRole("row").slice(1);
  expect(
    rows.map((row) => within(row).getAllByRole("cell")[0].textContent),
  ).toEqual(["CLM-1001", "CLM-1014", "CLM-1013"]);
  const first = within(rows[0]);
  expect(first.getByText("Decided")).toBeDefined();
  expect(first.getByText("Approved")).toBeDefined();
  expect(first.getByText("$420.00")).toBeDefined();
  expect(first.getByText("41 s")).toBeDefined();
  expect(within(rows[1]).getByText("In progress")).toBeDefined();
  expect(within(rows[2]).getByText("Waiting")).toBeDefined();
  const link = first.getByRole("link", { name: "CLM-1001" });
  expect(link.getAttribute("href")).toBe("/claims/CLM-1001");
  expect(panel.queryByText("Summary")).toBeNull();
});

it("shows a finished dispatch with its summary", async () => {
  showQueue(finished);
  const panel = await dispatchPanel();
  expect(await panel.findByText("Finished")).toBeDefined();
  expect(panel.getByText("2 min 41 s")).toBeDefined();
  const lines = within(panel.getByRole("list", { name: "Summary" }))
    .getAllByRole("listitem")
    .map((line) => line.textContent);
  expect(lines).toEqual([
    "3 approved, 1 declined and 1 referred.",
    "Waiting for sign-off: CLM-1008 $2,240.00, CLM-1011 $1,150.00",
    "Left for a handler: CLM-1016",
    "Left for the next dispatch: CLM-1012",
  ]);
  const held = panel.getByRole("link", { name: "CLM-1011" });
  expect(held.getAttribute("href")).toBe("/claims/CLM-1011");
});

it("shows a stopped dispatch", async () => {
  showQueue({ ...running, status: "stopped" });
  const panel = await dispatchPanel();
  const chip = await panel.findByText("Stopped");
  expect(chip.className).toBe("chip run-stopped");
  expect(
    panel.getByText(
      "It stopped before it finished. The next dispatch carries on its claims.",
    ),
  ).toBeDefined();
});

it("follows a dispatch as it works", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  const routes = showQueue(null);
  const panel = await dispatchPanel();
  expect(await panel.findByText("No dispatch yet.")).toBeDefined();

  routes["GET /api/dispatches/latest"] = { ...running, claims: [waiting] };
  await act(() => vi.advanceTimersByTimeAsync(REFRESH_MS));
  expect(panel.getByText("Waiting")).toBeDefined();

  routes["GET /api/dispatches/latest"] = finished;
  await act(() => vi.advanceTimersByTimeAsync(REFRESH_MS));
  expect(panel.getByText("Finished")).toBeDefined();
  expect(panel.queryByText("Waiting")).toBeNull();
});
