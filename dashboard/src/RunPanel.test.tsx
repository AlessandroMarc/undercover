import { act, cleanup, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { Run } from "./api";
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

const running: Run = {
  run_id: "run-1",
  cap: 5,
  status: "running",
  started_at: "2026-09-29T17:02:13+00:00",
  finished_at: null,
  summary: null,
  todos: [
    { content: "CLM-1001 Flight home canceled", status: "done" },
    {
      content: "CLM-1008 Trip canceled after a tornado",
      status: "in_progress",
    },
    { content: "CLM-1011 Suitcase lost", status: "to_do" },
    { content: "CLM-1018 Bag snatched", status: "left_for_handler" },
    { content: "Write the summary", status: "to_do" },
  ],
};

function showQueue(run: Run | null) {
  const routes: Routes = {
    "GET /api/claims": [claimSummary],
    "GET /api/runs/latest": run,
  };
  stubApi(routes);
  renderAt("/");
  return routes;
}

const runPanel = () => panel("Current run");

it("says when there's no run yet", async () => {
  showQueue(null);
  const panel = await runPanel();
  expect(await panel.findByText("No run yet.")).toBeDefined();
});

it("shows the to-do list of a running run", async () => {
  showQueue(running);
  const panel = await runPanel();
  expect(await panel.findByText("Running")).toBeDefined();
  expect(panel.getByText(/, up to 5 claims$/)).toBeDefined();
  const items = panel.getAllByRole("listitem");
  expect(items.map((item) => item.textContent)).toEqual([
    "DoneCLM-1001 Flight home canceled",
    "In progressCLM-1008 Trip canceled after a tornado",
    "To doCLM-1011 Suitcase lost",
    "Left for a handlerCLM-1018 Bag snatched",
    "To doWrite the summary",
  ]);
  expect(within(items[3]).getByText("Left for a handler").className).toBe(
    "chip todo-left_for_handler",
  );
  const link = panel.getByRole("link", { name: "CLM-1008" });
  expect(link.getAttribute("href")).toBe("/claims/CLM-1008");
  expect(panel.queryByText("Summary for the handlers")).toBeNull();
});

it("shows a finished run with its summary", async () => {
  showQueue({
    ...running,
    cap: 1,
    status: "finished",
    finished_at: "2026-09-29T17:05:40+00:00",
    summary: "Worked 1 claim: 1 approved.",
    todos: [{ content: "CLM-1001", status: "done" }],
  });
  const panel = await runPanel();
  expect(await panel.findByText("Finished")).toBeDefined();
  expect(panel.getByText(/up to 1 claim, finished at/)).toBeDefined();
  expect(panel.getByText("Summary for the handlers")).toBeDefined();
  expect(panel.getByText("Worked 1 claim: 1 approved.")).toBeDefined();
});

it("says when the agent hasn't written its list yet", async () => {
  showQueue({ ...running, todos: [] });
  const panel = await runPanel();
  expect(
    await panel.findByText("The agent hasn't written its to-do list yet."),
  ).toBeDefined();
});

it("ticks off the to-do list as the agent works", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  const routes = showQueue(null);
  const panel = await runPanel();
  expect(await panel.findByText("No run yet.")).toBeDefined();

  routes["GET /api/runs/latest"] = {
    ...running,
    todos: [{ content: "CLM-1001", status: "to_do" }],
  };
  await act(() => vi.advanceTimersByTimeAsync(REFRESH_MS));
  expect(panel.getByText("To do")).toBeDefined();

  routes["GET /api/runs/latest"] = {
    ...running,
    todos: [{ content: "CLM-1001", status: "done" }],
  };
  await act(() => vi.advanceTimersByTimeAsync(REFRESH_MS));
  expect(panel.getByText("Done")).toBeDefined();
  expect(panel.queryByText("To do")).toBeNull();
});
