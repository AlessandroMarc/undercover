import { expect, test } from "@playwright/test";
import { started, stopTheWork } from "./api";

// Starting runs on the dashboard creates them and reaches the stand-in for the
// agent, which accepts them and starts nothing.

test.afterEach(async ({ request }) => {
  await stopTheWork(request);
});

test("a dispatch started on the queue page reaches the agent", async ({
  page,
  request,
}) => {
  await page.goto("/");
  const panel = page.getByRole("region", { name: "Dispatch" });
  await panel
    .getByRole("combobox", { name: "Claim agents at once" })
    .selectOption("7");
  const button = panel.getByRole("button", { name: "Start a dispatch" });
  await button.click();
  await expect
    .poll(() => started(request))
    .toContainEqual(expect.objectContaining({ operation: "work_run" }));
  await expect(button).toHaveAttribute("aria-disabled", "false");
  await expect(panel.getByRole("alert")).toHaveCount(0);
  await expect(panel.getByText(/with 7 claim agents at once/)).toBeVisible();

  await button.click();
  await expect(panel.getByRole("alert")).toHaveText("A dispatch is running");
});

test("an evaluation started on the Scoreboard reaches the agent", async ({
  page,
  request,
}) => {
  await page.goto("/");
  await page.getByRole("link", { name: "Scoreboard" }).click();
  await expect(page).toHaveURL("/scoreboard");
  const form = page.getByRole("region", { name: "Start an evaluation" });
  await form
    .getByRole("combobox", { name: "Set" })
    .selectOption("Held-out set");
  await form
    .getByRole("combobox", { name: "Claims" })
    .selectOption("The five tiny claims");
  await form
    .getByRole("combobox", { name: "Claim agents at once" })
    .selectOption("5");
  const button = form.getByRole("button", { name: "Start an evaluation" });
  await button.click();
  await expect
    .poll(() => started(request))
    .toContainEqual(expect.objectContaining({ operation: "work_run" }));
  await expect(button).toHaveAttribute("aria-disabled", "false");
  await expect(form.getByRole("alert")).toHaveCount(0);
});
