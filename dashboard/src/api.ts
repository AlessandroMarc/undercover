import type {
  Claim,
  ClaimSummary,
  Customer,
  Handler,
  Policy,
  Run,
  Step,
} from "./types";

async function fetchOk(path: string, init?: RequestInit): Promise<Response> {
  const response = await fetch(path, init);
  if (!response.ok) {
    throw new Error(`${path} returned ${String(response.status)}`);
  }
  return response;
}

async function getJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetchOk(path, init);
  return (await response.json()) as T;
}

export const getQueue = () => getJson<ClaimSummary[]>("/api/claims");

export async function getClaimView(
  claimId: string,
): Promise<{ claim: Claim; steps: Step[] }> {
  const [claim, steps] = await Promise.all([
    getJson<Claim>(`/api/claims/${claimId}`),
    getJson<Step[]>(`/api/claims/${claimId}/steps`),
  ]);
  return { claim, steps };
}

export async function getPolicyView(
  policyId: string,
  customerId: string,
): Promise<{ policy: Policy; customer: Customer }> {
  const [policy, customer] = await Promise.all([
    getJson<Policy>(`/api/policies/${policyId}`),
    getJson<Customer>(`/api/customers/${customerId}`),
  ]);
  return { policy, customer };
}

export const getHandlers = () => getJson<Handler[]>("/api/handlers");

export const getLatestRun = () => getJson<Run | null>("/api/runs/latest");

async function getText(path: string): Promise<string> {
  const response = await fetchOk(path);
  return response.text();
}

export async function getInstructions(): Promise<{
  queue: string;
  claim: string;
}> {
  const [queue, claim] = await Promise.all([
    getText("/api/instructions/queue"),
    getText("/api/instructions/claim"),
  ]);
  return { queue, claim };
}

export const signOff = (claimId: string, handlerId: string) =>
  getJson<Claim>(`/api/claims/${claimId}/sign-off`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ handler_id: handlerId }),
  });
