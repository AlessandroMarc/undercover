import { expect, test } from "@playwright/test";
import { post, put } from "./api";

// These tests stand in for the agent's service and its claim agents by calling
// the API through the dashboard's proxy, and watch the pages update without a
// reload. Only this file records dispatches, and it uses claims no other test
// touches.

test("the dispatch panel follows a dispatch as it works", async ({
  page,
  request,
}) => {
  await page.goto("/");
  const panel = page.getByRole("region", { name: "Dispatch" });
  await expect(panel).toBeVisible();

  const response = await post(request, "/api/runs/dispatches", {
    agents: 2,
    model: "openai/gpt-6-luna",
    reasoning_effort: "low",
  });
  const { run_id } = (await response.json()) as { run_id: string };
  await put(request, `/api/runs/${run_id}/claims`, {
    claim_ids: ["CLM-1013", "CLM-1014"],
  });
  const rows = panel.getByRole("row");
  await expect(panel.getByText("Running", { exact: true })).toBeVisible();
  await expect(panel.getByText(/with 2 claim agents at once/)).toBeVisible();
  await expect(rows).toHaveText([
    /^Claim/,
    /^CLM-1013.*Waiting/,
    /^CLM-1014.*Waiting/,
  ]);

  for (const [claimId, thread] of [
    ["CLM-1013", "e2e-5"],
    ["CLM-1014", "e2e-6"],
  ]) {
    await post(request, `/api/claims/${claimId}/start`, { thread_id: thread });
    await post(request, `/api/claims/${claimId}/model-calls`, {
      run_id,
      input_tokens: 1200,
      output_tokens: 300,
      cost: 0.005,
    });
  }
  await expect(rows).toHaveText([
    /^Claim/,
    /^CLM-1013.*In progress/,
    /^CLM-1014.*In progress/,
  ]);

  await post(request, "/api/claims/CLM-1013/decision", {
    decision: "approve",
    payout: 300,
    section: "Section 3, Trip Delay",
    reason: "The delay was covered.",
  });
  await post(request, "/api/claims/CLM-1013/payment", { amount: 300 });
  await post(request, "/api/claims/CLM-1014/decision", {
    decision: "refer",
    payout: 0,
    section: "Manual, section 2",
    reason: "The airline's report is missing.",
  });
  for (const claimId of ["CLM-1013", "CLM-1014"])
    await post(request, `/api/claims/${claimId}/work-times`, {
      run_id,
      seconds: 41,
    });
  await expect(rows).toHaveText([
    /^Claim/,
    /^CLM-1013.*Decided.*Approved.*\$300\.00.*41 s.*\$0\.0050/,
    /^CLM-1014.*Decided.*Referred.*41 s.*\$0\.0050/,
  ]);

  await post(request, `/api/runs/${run_id}/finish`, {});
  await expect(panel.getByText("Finished", { exact: true })).toBeVisible();
  await expect(
    panel.getByText("1 approved, 0 declined and 1 referred."),
  ).toBeVisible();
  await expect(
    panel.getByText(/Model cost \$0\.0100, took \d+ s\./),
  ).toBeVisible();

  await rows.nth(1).getByRole("link", { name: "CLM-1013" }).click();
  await expect(page).toHaveURL("/claims/CLM-1013");
});

test("a claim that fails twice is left for a handler", async ({
  page,
  request,
}) => {
  await page.goto("/claims/CLM-1016");
  const heading = page.locator(".claim-heading");
  await expect(heading.getByText("Waiting")).toBeVisible();

  await post(request, "/api/claims/CLM-1016/start", { thread_id: "e2e-3" });
  await post(request, "/api/claims/CLM-1016/steps", {
    kind: "reading",
    content: "Policy wording, section 7: Emergency Medical",
  });
  await post(request, "/api/claims/CLM-1016/failure", {
    reason: "RuntimeError: The model timed out",
  });
  await expect(
    page.getByText("Back in the queue after a failed attempt."),
  ).toBeVisible();

  await post(request, "/api/claims/CLM-1016/start", { thread_id: "e2e-4" });
  await post(request, "/api/claims/CLM-1016/failure", {
    reason: "RuntimeError: The model timed out again",
  });
  await expect(heading.getByText("Left for a handler")).toBeVisible();
  await expect(
    page.getByText(
      "The agent couldn't finish this claim in 2 attempts, so it's left for a handler.",
    ),
  ).toBeVisible();

  const read = page.locator(".sections-read");
  await expect(read.getByRole("listitem")).toHaveText([
    "Policy wording, section 7: Emergency Medical",
  ]);
  const failed = page.locator(".step", { hasText: "Failed" });
  await expect(failed).toHaveText([
    /Failed RuntimeError: The model timed out$/,
    /Failed RuntimeError: The model timed out again$/,
  ]);
});
