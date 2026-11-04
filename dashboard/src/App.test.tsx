import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { App } from "./App";
import { claimRoutes, claim, queue, stubApi } from "./test-utils";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.location.hash = "";
});

const routes = {
  ...claimRoutes(claim),
  "GET /api/claims": queue,
  "GET /api/instructions": "# UnderCover Agent instructions",
};

it("starts on the queue", async () => {
  stubApi(routes);
  render(<App />);
  expect(await screen.findByText("CLM-1004")).toBeDefined();
  expect(
    screen.getByText("Here is where your claims stand today."),
  ).toBeDefined();
});

it("opens a claim from its hash", async () => {
  stubApi(routes);
  window.location.hash = "#/claims/CLM-1001";
  render(<App />);
  expect(await screen.findByText("Hotel receipt")).toBeDefined();
});

it("opens the instructions from the navigation", async () => {
  stubApi(routes);
  window.location.hash = "#/instructions";
  render(<App />);
  expect(
    await screen.findByText("UnderCover Agent instructions"),
  ).toBeDefined();
  expect(
    screen
      .getByRole("link", { name: "Agent instructions" })
      .getAttribute("aria-current"),
  ).toBe("page");
});
