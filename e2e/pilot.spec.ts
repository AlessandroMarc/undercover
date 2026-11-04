import { expect, test, type APIRequestContext } from "@playwright/test";

async function post(
  request: APIRequestContext,
  path: string,
  data: Record<string, unknown>,
) {
  return request.post(`/api/claims/${path}`, { data });
}

async function decide(
  request: APIRequestContext,
  claimId: string,
  payout: number,
  section: string,
) {
  await post(request, `${claimId}/start`, {});
  await post(request, `${claimId}/steps`, {
    kind: "tool_call",
    text: `get_claim(claim_id='${claimId}')`,
  });
  await post(request, `${claimId}/steps`, {
    kind: "message",
    text: "The claim is covered.",
  });
  await post(request, `${claimId}/decision`, {
    decision: "approve",
    payout,
    explanation: `Covered under section ${section}.`,
    policy_section: section,
  });
}

test("the queue shows 25 claims and a claim moving", async ({
  page,
  request,
}) => {
  await page.goto("/");
  await expect(page.getByText("25 claims")).toBeVisible();
  const row = page.getByRole("row", { name: /CLM-1010/ });
  await expect(row.getByText("Waiting")).toBeVisible();

  await post(request, "CLM-1010/start", {});
  await expect(row.getByText("In progress")).toBeVisible({ timeout: 10_000 });
});

test("a claim under $1,000 shows its decision, reasons, payment and steps", async ({
  page,
  request,
}) => {
  await decide(request, "CLM-1001", 420, "3. Trip Delay");
  await post(request, "CLM-1001/payment", { amount: 420 });

  await page.goto("/#/claims/CLM-1001");
  await expect(
    page.getByRole("heading", { name: "Claim CLM-1001" }),
  ).toBeVisible();
  await expect(page.getByText("Approved").first()).toBeVisible();
  await expect(page.getByText("$420.00").first()).toBeVisible();
  await expect(
    page.getByText("Covered under section 3. Trip Delay."),
  ).toBeVisible();
  await expect(page.getByText("get_claim(claim_id='CLM-1001')")).toBeVisible();
  await expect(page.getByText("The claim is covered.")).toBeVisible();
  await expect(page.getByText(/^Paid \$420\.00 on/)).toBeVisible();
});

test("a payout over $1,000 is blocked until a handler signs off", async ({
  page,
  request,
}) => {
  await decide(request, "CLM-1002", 1250, "5. Baggage and Personal Effects");

  const blocked = await post(request, "CLM-1002/payment", { amount: 1250 });
  expect(blocked.status()).toBe(409);

  await page.goto("/#/claims/CLM-1002");
  await expect(page.getByText("Needs sign-off")).toBeVisible();
  await page.getByLabel("Handler").selectOption({ label: "Priya Raman" });
  await page.getByRole("button", { name: "Sign off" }).click();

  await expect(page.getByText(/^Signed off by Priya Raman on/)).toBeVisible();
  await expect(page.getByText(/^Paid \$1,250\.00 on/)).toBeVisible();
  const claim = await request.get("/api/claims/CLM-1002");
  expect(
    ((await claim.json()) as { payment: { amount: number } }).payment.amount,
  ).toBe(1250);
});

test("the instructions are there to read and not to edit", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: "Agent instructions" }).click();
  await expect(
    page.getByRole("heading", { name: "UnderCover Agent instructions" }),
  ).toBeVisible();
  await expect(page.getByRole("textbox")).toHaveCount(0);
});
