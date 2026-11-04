import { vi } from "vitest";
import type {
  Claim,
  ClaimSummary,
  Customer,
  Handler,
  Policy,
  Step,
} from "./types";

export function stubApi(routes: Record<string, unknown>) {
  const fetchMock = vi.fn((input: string, init?: RequestInit) => {
    const key = `${init?.method ?? "GET"} ${input}`;
    if (!(key in routes)) {
      return Promise.resolve(new Response("{}", { status: 404 }));
    }
    const body = routes[key];
    return Promise.resolve(
      new Response(typeof body === "string" ? body : JSON.stringify(body)),
    );
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

export const claim: Claim = {
  claim_id: "CLM-1001",
  policy_id: "POL-2001",
  customer_id: "CUS-3001",
  claim_type: "trip_delay",
  submitted_on: "2026-06-24",
  incident_date: "2026-06-18",
  incident_location: "Rome, Italy",
  summary: "Flight home canceled by the airline",
  story: "My flight was canceled and I stayed the night.",
  items: [
    { description: "Airport hotel", category: "accommodation", amount: 245 },
    { description: "Dinner and breakfast", category: "meals", amount: 95 },
  ],
  amount_claimed: 340,
  documents: [
    {
      name: "Hotel receipt",
      type: "receipt",
      content: "Hotel Aurelia, $245.00.",
    },
  ],
  status: "waiting",
  decision: null,
  payment: null,
  sign_off: null,
};

export const decided: Claim = {
  ...claim,
  status: "decided",
  decision: {
    decision: "approve",
    payout: 340,
    explanation: "The delay was long enough and the receipts agree.",
    policy_section: "3. Trip Delay",
  },
  payment: { amount: 340, paid_on: "2026-11-04T14:30:00" },
};

export const awaitingSignOff: Claim = {
  ...claim,
  status: "awaiting_signoff",
  decision: {
    decision: "approve",
    payout: 1250,
    explanation: "Covered up to the plan maximum.",
    policy_section: "5. Baggage and Personal Effects",
  },
};

export const steps: Step[] = [
  {
    id: 1,
    kind: "tool_call",
    text: "get_claim(claim_id='CLM-1001')",
    created_at: "2026-11-04T14:29:00",
  },
  {
    id: 2,
    kind: "message",
    text: "I have what I need.",
    created_at: "2026-11-04T14:29:30",
  },
];

export const policy: Policy = {
  policy_id: "POL-2001",
  customer_id: "CUS-3001",
  plan: "premium",
  add_ons: ["electronics_plus"],
  purchased_on: "2026-04-22",
  sold_through: "Meridian Air checkout",
  trip: {
    destination: "Rome, Italy",
    departs_on: "2026-06-10",
    returns_on: "2026-06-18",
    trip_cost: 3100,
  },
  travelers: ["Maya Patel"],
  status: "active",
};

export const customer: Customer = {
  customer_id: "CUS-3001",
  name: "Maya Patel",
  customer_since: "2023-04-11",
  previous_claims: [
    {
      claim_id: "CLM-0412",
      filed_on: "2024-08-19",
      incident_date: "2024-08-09",
      claim_type: "baggage_delay",
      summary: "Checked bag arrived 30 hours late",
      outcome: "approved",
      amount_paid: 140,
    },
  ],
};

export const handlers: Handler[] = [
  {
    handler_id: "HND-01",
    name: "Dana Whitfield",
    role: "Senior Claims Handler",
    can_approve_over_limit: true,
  },
  {
    handler_id: "HND-02",
    name: "Marcus Oyelaran",
    role: "Claims Handler",
    can_approve_over_limit: true,
  },
];

export const queue: ClaimSummary[] = [
  {
    claim_id: "CLM-1001",
    customer_name: "Maya Patel",
    claim_type: "trip_delay",
    summary: "Flight canceled",
    amount_claimed: 420,
    status: "decided",
    decision: "approve",
    payout: 420,
  },
  {
    claim_id: "CLM-1002",
    customer_name: "Tom Becker",
    claim_type: "baggage",
    summary: "Stolen bag",
    amount_claimed: 1500,
    status: "awaiting_signoff",
    decision: "approve",
    payout: 1250,
  },
  {
    claim_id: "CLM-1003",
    customer_name: "Ana Souza",
    claim_type: "emergency_medical",
    summary: "Broken wrist",
    amount_claimed: 800,
    status: "in_progress",
    decision: null,
    payout: null,
  },
  {
    claim_id: "CLM-1004",
    customer_name: "Lee Chen",
    claim_type: "passport",
    summary: "Lost passport",
    amount_claimed: 150,
    status: "waiting",
    decision: null,
    payout: null,
  },
];

export const claimRoutes = (record: Claim) => ({
  "GET /api/claims/CLM-1001": record,
  "GET /api/claims/CLM-1001/steps": steps,
  "GET /api/policies/POL-2001": policy,
  "GET /api/customers/CUS-3001": customer,
  "GET /api/handlers": handlers,
});
