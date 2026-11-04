import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { QueuePage } from "./QueuePage";
import { queue, stubApi } from "./test-utils";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it("lists every claim with its status, amounts and counts", async () => {
  stubApi({ "GET /api/claims": queue });
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
