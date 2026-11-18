import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { StatusBadge } from "./StatusBadge";
import type { DecisionKind, Status } from "./types";

afterEach(cleanup);

const cases: [Status, DecisionKind | null, string, string][] = [
  ["waiting", null, "Waiting", "cerulean"],
  ["in_progress", null, "In progress", "marigold"],
  ["awaiting_signoff", "approve", "Needs sign-off", "coral"],
  ["needs_handler", null, "Left for a handler", "coral"],
  ["decided", "approve", "Approved", "green"],
  ["decided", "decline", "Declined", "raspberry"],
  ["decided", "refer", "Referred", "coral"],
];

it.each(cases)("shows %s with %s as %s", (status, decision, label, tone) => {
  render(<StatusBadge status={status} decision={decision} />);
  expect(screen.getByText(label).getAttribute("data-tone")).toBe(tone);
});
