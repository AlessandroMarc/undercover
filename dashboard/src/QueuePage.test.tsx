import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { QueuePage } from "./QueuePage";
import { finishedRun, queue, runningRun, stubApi } from "./test-utils";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it("lists every claim with its status, amounts and counts", async () => {
  stubApi({ "GET /api/claims": queue, "GET /api/runs/latest": null });
  render(<QueuePage />);

  expect(await screen.findByText("CLM-1001")).toBeDefined();
  expect(screen.getByText("4 claims")).toBeDefined();
  expect(screen.getByText("Maya Patel")).toBeDefined();
  expect(screen.getByText("Emergency medical")).toBeDefined();
  expect(screen.getByText("$1,500.00")).toBeDefined();
  expect(screen.getByText("$1,250.00")).toBeDefined();
  for (const label of [
    "Approved",
    "Needs sign-off",
    "In progress",
    "Waiting",
  ]) {
    expect(screen.getAllByText(label).length).toBeGreaterThan(0);
  }
  expect(screen.getAllByText("—")).toHaveLength(2);
  const link = screen.getByRole("link", { name: "CLM-1002" });
  expect(link.getAttribute("href")).toBe("#/claims/CLM-1002");
});

it("says what happened when the claims cannot be loaded", async () => {
  stubApi({});
  render(<QueuePage />);
  const alert = await screen.findByRole("alert");
  expect(alert.textContent).toContain("We could not load the claims.");
});

it("says there is no run yet", async () => {
  stubApi({ "GET /api/claims": queue, "GET /api/runs/latest": null });
  render(<QueuePage />);
  expect(await screen.findByText(/No run yet/)).toBeDefined();
});

it("shows the running run's to-do list with a badge for each item", async () => {
  stubApi({ "GET /api/claims": queue, "GET /api/runs/latest": runningRun });
  render(<QueuePage />);

  expect(await screen.findByText("CLM-1002 baggage")).toBeDefined();
  expect(screen.getByText("Running")).toBeDefined();
  expect(screen.getByText(/up to 5 claims\. 1 of 4 done\./)).toBeDefined();
  expect(screen.getByText("To do").getAttribute("data-tone")).toBe("cerulean");
  expect(screen.getByText("Done").getAttribute("data-tone")).toBe("green");
  expect(screen.getAllByText("Left for a handler").length).toBeGreaterThan(1);
  expect(screen.queryByText("Summary for the handlers")).toBeNull();
});

it("shows the summary when the run has finished", async () => {
  stubApi({ "GET /api/claims": queue, "GET /api/runs/latest": finishedRun });
  render(<QueuePage />);
  expect(
    await screen.findByText("Four claims worked. One waits for sign-off."),
  ).toBeDefined();
  expect(screen.getByText("Finished")).toBeDefined();
});

it("says the agent has not written its list yet", async () => {
  const empty = { ...runningRun, todos: [] };
  stubApi({ "GET /api/claims": queue, "GET /api/runs/latest": empty });
  render(<QueuePage />);
  expect(
    await screen.findByText(/has not written its to-do list/),
  ).toBeDefined();
});

it("counts the claims left for a handler", async () => {
  const left = { ...queue[3], status: "needs_handler" as const };
  stubApi({
    "GET /api/claims": [...queue.slice(0, 3), left],
    "GET /api/runs/latest": null,
  });
  render(<QueuePage />);
  expect(await screen.findAllByText("Left for a handler")).toHaveLength(2);
});
