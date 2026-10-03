import { type APIRequestContext, expect } from "@playwright/test";

// Stands in for the agent by sending to the API through the dashboard's proxy.
async function send(
  request: APIRequestContext,
  method: "POST" | "PUT",
  path: string,
  data: object,
) {
  const response = await request.fetch(path, { method, data });
  await expect(response).toBeOK();
  return response;
}

export const post = (request: APIRequestContext, path: string, data: object) =>
  send(request, "POST", path, data);

export const put = (request: APIRequestContext, path: string, data: object) =>
  send(request, "PUT", path, data);

// The stand-in for the agent's service, which Playwright starts on its own port.
export const AGENT_STAND_IN = "http://127.0.0.1:8003";

export async function resumed(request: APIRequestContext): Promise<string[]> {
  const response = await request.get(`${AGENT_STAND_IN}/api/resumed`);
  await expect(response).toBeOK();
  return (await response.json()) as string[];
}
