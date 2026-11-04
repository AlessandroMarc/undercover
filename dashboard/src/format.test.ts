import { expect, it } from "vitest";
import {
  formatCount,
  formatDate,
  formatDateTime,
  formatMoney,
  formatRelative,
  humanize,
} from "./format";

it("formats money in dollars with two decimals", () => {
  expect(formatMoney(1250)).toBe("$1,250.00");
  expect(formatMoney(0)).toBe("$0.00");
  expect(formatMoney(-1250)).toBe("−$1,250.00");
});

it("formats dates and times", () => {
  expect(formatDate("2026-06-18")).toBe("Jun 18, 2026");
  expect(formatDateTime("2026-11-04T14:30:00")).toBe("Nov 4, 2026, 2:30 PM");
});

it("formats counts with the noun", () => {
  expect(formatCount(1, "claim")).toBe("1 claim");
  expect(formatCount(1204, "claim")).toBe("1,204 claims");
});

it("formats recent times as relative and older times as dates", () => {
  const now = new Date("2026-11-04T12:00:00Z");
  const ago = (ms: number) => new Date(now.getTime() - ms).toISOString();
  expect(formatRelative(ago(30_000), now)).toBe("Just now");
  expect(formatRelative(ago(5 * 60_000), now)).toBe("5 min ago");
  expect(formatRelative(ago(3_600_000), now)).toBe("1 hour ago");
  expect(formatRelative(ago(3 * 3_600_000), now)).toBe("3 hours ago");
  expect(formatRelative(ago(86_400_000), now)).toBe("1 day ago");
  expect(formatRelative(ago(2 * 86_400_000), now)).toBe("2 days ago");
  expect(formatRelative(ago(8 * 86_400_000), now)).toContain("Oct 27, 2026");
});

it("turns codes into labels", () => {
  expect(humanize("trip_delay")).toBe("Trip delay");
});
