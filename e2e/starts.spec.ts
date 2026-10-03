import { expect, test } from "@playwright/test";
import { started } from "./api";

// Starting runs on the dashboard reaches the stand-in for the agent's service,
// which accepts them and starts nothing.

test("a dispatch started on the queue page reaches the agent's service", async ({
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
    .toContainEqual({ path: "/api/dispatches", body: { agents: 7 } });
  await expect(button).toHaveAttribute("aria-disabled", "false");
  await expect(panel.getByRole("alert")).toHaveCount(0);
});
