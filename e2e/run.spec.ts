import { type APIRequestContext, expect, test } from "@playwright/test";

// These tests stand in for the queue agent and a claim agent by calling the
// API through the dashboard's proxy, and watch the pages update without a
// reload. Only this file starts runs, and it uses claims no other test touches.

async function send(request: APIRequestContext, path: string, data: object) {
  const response = await request.post(path, { data });
  expect(response.ok()).toBe(true);
  return response;
}

test("the queue shows the agent's to-do list as it works", async ({
  page,
  request,
}) => {
  await page.goto("/");
  const panel = page.locator("section", {
    has: page.getByRole("heading", { name: "Current run" }),
  });
  await expect(panel).toBeVisible();

  const response = await send(request, "/api/runs", { cap: 2 });
  const { run_id } = (await response.json()) as { run_id: string };
  const write = async (first: string, second: string) => {
    const written = await request.put(`/api/runs/${run_id}/todos`, {
      data: {
        todos: [
          {
            content: "CLM-1013 Seven hour delay leaving Chicago",
            status: first,
          },
          { content: "CLM-1014 Duffel bag lost", status: second },
        ],
      },
    });
    expect(written.ok()).toBe(true);
  };
  const items = panel.getByRole("listitem");

  await write("to_do", "to_do");
  await expect(panel.getByText("Running", { exact: true })).toBeVisible();
  await expect(items).toHaveText([/^To do.*CLM-1013/, /^To do.*CLM-1014/]);

  await write("in_progress", "to_do");
  await expect(items).toHaveText([
    /^In progress.*CLM-1013/,
    /^To do.*CLM-1014/,
  ]);

  await write("done", "in_progress");
  await expect(items).toHaveText([/^Done.*CLM-1013/, /^In progress.*CLM-1014/]);

  await send(request, `/api/runs/${run_id}/finish`, {
    summary: "Worked 2 claims: 2 approved.",
  });
  await expect(panel.getByText("Finished", { exact: true })).toBeVisible();
  await expect(panel.getByText("Summary for the handlers")).toBeVisible();
  await expect(panel.getByText("Worked 2 claims: 2 approved.")).toBeVisible();

  await items.first().getByRole("link", { name: "CLM-1013" }).click();
  await expect(page).toHaveURL("/claims/CLM-1013");
});

test("a claim that fails twice is left for a handler", async ({
  page,
  request,
}) => {
  await page.goto("/claims/CLM-1016");
  const heading = page.locator(".claim-heading");
  await expect(heading.getByText("Waiting")).toBeVisible();

  await send(request, "/api/claims/CLM-1016/start", { thread_id: "e2e-3" });
  await send(request, "/api/claims/CLM-1016/steps", {
    kind: "reading",
    content: "Policy wording, section 7: Emergency Medical",
  });
  await send(request, "/api/claims/CLM-1016/failure", {
    reason: "RuntimeError: The model timed out",
  });
  await expect(
    page.getByText("Back in the queue after a failed attempt."),
  ).toBeVisible();

  await send(request, "/api/claims/CLM-1016/start", { thread_id: "e2e-4" });
  await send(request, "/api/claims/CLM-1016/failure", {
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
