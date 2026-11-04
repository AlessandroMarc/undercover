import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ClaimPage } from "./ClaimPage";
import type { Claim } from "./types";
import {
  awaitingSignOff,
  claim,
  claimRoutes,
  decided,
  stubApi,
} from "./test-utils";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it("shows a waiting claim in full with no decision yet", async () => {
  stubApi({ ...claimRoutes(claim), "GET /api/claims/CLM-1001/steps": [] });
  render(<ClaimPage claimId="CLM-1001" />);

  expect(await screen.findByText("Hotel receipt")).toBeDefined();
  expect(
    screen.getByText(/The agent has not decided this claim yet/),
  ).toBeDefined();
  expect(screen.getByText(/No steps yet/)).toBeDefined();
  expect(
    screen.getByText("My flight was canceled and I stayed the night."),
  ).toBeDefined();
  expect(screen.getByText("$245.00")).toBeDefined();
  expect(await screen.findByText("Electronics Plus")).toBeDefined();
  expect(screen.getAllByText("Jun 18, 2026")).toHaveLength(2);
  expect(screen.getByText("CLM-0412")).toBeDefined();
  expect(screen.getByText("Waiting")).toBeDefined();
});

it("shows a decided claim with its reasons, payment and steps", async () => {
  stubApi(claimRoutes(decided));
  render(<ClaimPage claimId="CLM-1001" />);

  expect(await screen.findByText("3. Trip Delay")).toBeDefined();
  expect(await screen.findByText("CLM-0412")).toBeDefined();
  expect(
    screen.getByText("The delay was long enough and the receipts agree."),
  ).toBeDefined();
  expect(screen.getAllByText("Approved")).toHaveLength(2);
  expect(
    screen.getByText("Paid $340.00 on Nov 4, 2026, 2:30 PM."),
  ).toBeDefined();
  expect(screen.getByText("get_claim(claim_id='CLM-1001')")).toBeDefined();
  expect(screen.getByText("I have what I need.")).toBeDefined();
  expect(screen.queryByRole("button", { name: "Sign off" })).toBeNull();
});

it("lets a handler sign off a payout over the limit", async () => {
  const signedOff: Claim = {
    ...awaitingSignOff,
    status: "decided",
    sign_off: {
      handler_id: "HND-02",
      handler_name: "Marcus Oyelaran",
      signed_off_on: "2026-11-04T15:00:00",
    },
    payment: { amount: 1250, paid_on: "2026-11-04T15:00:00" },
  };
  stubApi(claimRoutes(awaitingSignOff));
  render(<ClaimPage claimId="CLM-1001" />);

  const button = await screen.findByRole("button", { name: "Sign off" });
  expect(screen.getByText("Needs sign-off")).toBeDefined();
  expect(screen.getByText(/waits for a handler's sign-off/)).toBeDefined();
  expect((button as HTMLButtonElement).disabled).toBe(true);

  await screen.findByRole("option", { name: "Marcus Oyelaran" });
  fireEvent.change(screen.getByLabelText("Handler"), {
    target: { value: "HND-02" },
  });
  expect((button as HTMLButtonElement).disabled).toBe(false);

  stubApi({
    ...claimRoutes(signedOff),
    "POST /api/claims/CLM-1001/sign-off": signedOff,
  });
  fireEvent.click(button);

  expect(
    await screen.findByText(
      "Signed off by Marcus Oyelaran on Nov 4, 2026, 3:00 PM.",
    ),
  ).toBeDefined();
});

it("sends the chosen handler when signing off", async () => {
  const fetchMock = stubApi({
    ...claimRoutes(awaitingSignOff),
    "POST /api/claims/CLM-1001/sign-off": awaitingSignOff,
  });
  render(<ClaimPage claimId="CLM-1001" />);
  await screen.findByRole("option", { name: "Dana Whitfield" });
  fireEvent.change(screen.getByLabelText("Handler"), {
    target: { value: "HND-01" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Sign off" }));

  await waitFor(() => {
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/claims/CLM-1001/sign-off",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ handler_id: "HND-01" }),
      }),
    );
  });
});

it("says what happened when a sign-off fails", async () => {
  stubApi(claimRoutes(awaitingSignOff));
  render(<ClaimPage claimId="CLM-1001" />);
  await screen.findByRole("option", { name: "Dana Whitfield" });
  fireEvent.change(screen.getByLabelText("Handler"), {
    target: { value: "HND-01" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Sign off" }));
  expect((await screen.findByRole("alert")).textContent).toBe(
    "We could not record the sign-off. Try again.",
  );
});

it("copies the claim ID", async () => {
  stubApi(claimRoutes(claim));
  const writeText = vi.fn().mockResolvedValue(undefined);
  vi.stubGlobal("navigator", { clipboard: { writeText } });
  render(<ClaimPage claimId="CLM-1001" />);

  fireEvent.click(screen.getByRole("button", { name: "Copy ID" }));
  expect(await screen.findByRole("button", { name: "Copied" })).toBeDefined();
  expect(writeText).toHaveBeenCalledWith("CLM-1001");
});

it("says what happened when the claim does not exist", async () => {
  stubApi({});
  render(<ClaimPage claimId="CLM-0000" />);
  expect((await screen.findByRole("alert")).textContent).toContain(
    "We could not load this claim.",
  );
});
