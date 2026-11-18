import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { InstructionsPage } from "./InstructionsPage";
import { stubApi } from "./test-utils";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const text = [
  "## Steps",
  "1. Call `get_claim` first.",
  "   - **approve**: covered.",
  "",
  "A note.",
  "",
  "2. Then decide.",
].join("\n");

it("shows the instructions read only", async () => {
  stubApi({
    "GET /api/instructions/queue": "You run the queue.",
    "GET /api/instructions/claim": text,
  });
  render(<InstructionsPage />);

  expect(
    await screen.findByRole("heading", { name: "Running the queue" }),
  ).toBeDefined();
  expect(
    screen.getByRole("heading", { name: "Working a claim" }),
  ).toBeDefined();
  expect(screen.getByText("You run the queue.")).toBeDefined();
  expect(screen.getByText("get_claim").tagName).toBe("CODE");
  expect(screen.getByText("approve").tagName).toBe("STRONG");
  const lists = screen.getAllByRole("list");
  expect(lists[2]?.getAttribute("start")).toBe("2");
  expect(screen.queryByRole("textbox")).toBeNull();
  expect(screen.queryByRole("button")).toBeNull();
});

it("says what happened when the instructions cannot be loaded", async () => {
  stubApi({});
  render(<InstructionsPage />);
  expect((await screen.findByRole("alert")).textContent).toContain(
    "We could not load the instructions.",
  );
});
