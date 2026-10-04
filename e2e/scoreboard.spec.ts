import { expect, test } from "@playwright/test";
import { post } from "./api";

// This test stands in for the agent's service and its claim agents, playing
// out an evaluation of the held-out set's tiny claims through the API, and
// checks the Scoreboard and the evaluation's page. Only this file records
// evaluations, and its copies are its own.

interface Created {
  run_id: string;
  number: number;
  claims: { claim_id: string }[];
}

test("the Scoreboard shows an evaluation played out through the API", async ({
  page,
  request,
}) => {
  const response = await post(request, "/api/runs/evaluations", {
    evaluation_set: "held_out",
    tiny: true,
    agents: 5,
    model: "openai/gpt-6-luna",
    reasoning_effort: "low",
  });
  const { run_id, number, claims } = (await response.json()) as Created;
  const copyOf = (original: string) => `${original}-E${String(number)}`;
  expect(claims).toHaveLength(5);

  for (const { claim_id } of claims) {
    await post(request, `/api/claims/${claim_id}/start`, {
      thread_id: `e2e-${claim_id}`,
    });
    await post(request, `/api/claims/${claim_id}/model-calls`, {
      run_id,
      input_tokens: 1200,
      output_tokens: 300,
      cost: 0.0125,
    });
    await post(request, `/api/claims/${claim_id}/work-times`, {
      run_id,
      seconds: 40,
    });
  }
  const decide = (original: string, decision: string, payout: number) =>
    post(request, `/api/claims/${copyOf(original)}/decision`, {
      decision,
      payout,
      section: "Section 5",
      reason: `The agent's reason on ${original}.`,
    });
  const pay = (original: string, amount: number) =>
    post(request, `/api/claims/${copyOf(original)}/payment`, { amount });
  await decide("CLM-1104", "approve", 250);
  await pay("CLM-1104", 250);
  await decide("CLM-1106", "approve", 300);
  await pay("CLM-1106", 300);
  await decide("CLM-1110", "refer", 0);
  await decide("CLM-1112", "approve", 1200);
  await post(request, `/api/runs/${run_id}/finish`, {});

  await page.goto("/scoreboard");
  const evaluation = `Evaluation #${String(number)}`;
  const row = page.getByRole("row", { name: new RegExp(`^${evaluation} `) });
  await expect(row.getByText("Finished")).toBeVisible();
  for (const shown of ["80%", "40%", "$620.00", "60%", "$0.0125", "40 s"])
    await expect(row.getByText(shown, { exact: true })).toBeVisible();

  await row.getByRole("link", { name: evaluation }).click();
  await expect(page).toHaveURL(`/scoreboard/${run_id}`);
  const scored = page.getByRole("region", { name: "Claims" });
  for (const original of ["CLM-1106", "CLM-1112", "CLM-1114"])
    await expect(
      scored
        .getByRole("row", { name: new RegExp(copyOf(original)) })
        .getByText("Miss"),
    ).toBeVisible();
  for (const original of ["CLM-1104", "CLM-1110"])
    await expect(
      scored
        .getByRole("row", { name: new RegExp(copyOf(original)) })
        .getByText("Right"),
    ).toBeVisible();
  await expect(
    scored.getByRole("row", { name: new RegExp(copyOf("CLM-1114")) }),
  ).toContainText("No decision");

  await scored.getByRole("link", { name: copyOf("CLM-1112") }).click();
  await expect(page).toHaveURL(`/claims/${copyOf("CLM-1112")}`);
  await expect(
    page.getByText("A copy of CLM-1112 in an evaluation"),
  ).toBeVisible();
  await expect(
    page.getByText(
      "Held for sign-off. In an evaluation this counts as finished, and a copy can't be signed off.",
    ),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Sign off" })).toHaveCount(0);
});
