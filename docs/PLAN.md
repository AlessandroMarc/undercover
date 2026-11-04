# Plan: the claims pilot

This plan builds the pilot described in `docs/SPEC.md`: a backend that holds the claims queue, a dashboard for the three handlers, and the UnderCover Agent that decides claims. It follows `docs/TECH_STACK.md`, `docs/CODE_STANDARDS.md`, `docs/PROCESS.md` and `docs/BRAND.md`. The repo is a hello-world skeleton today (`docs/STATUS.md`), so everything below is new.

## How the pieces fit

```
data/*.json, policy_wording.md --seed--> backend (FastAPI + SQLite) <--HTTP-- agent (create_agent on OpenRouter)
                                              ^
                                              +--HTTP (proxied /api)-- dashboard (React, Vite)
```

- The backend owns all state. The agent and the dashboard talk to it only through `/api`.
- The agent never opens a file in `data/`. It gets claims, policies, customers, plans, the policy wording and its own instructions from API operations. Nothing in the backend reads `data/evals/`, `data/security/` or `claims_manual.md`.
- One agent run is one claim. A small runner script works the whole queue claim by claim.

## Decisions to review

These are my choices where the spec is silent. Tell me if you want any of them different before I implement.

1. **Claim states.** `waiting` (seeded as the queue), `in_progress` (the agent has started), `awaiting_signoff` (approved over $1,000, payment blocked) and `decided` (approve with payment allowed, decline or refer). The seed data marks every claim `open`; I map that to `waiting`.
2. **How the $1,000 rule is enforced.** The backend's `pay_claim` operation refuses with a 409 when the amount is over `payout_approval_limit` (from `company.json`) and no handler has signed off. It also refuses on a claim that is not approved or when the amount differs from the approved payout. A handler signing off through the dashboard records the sign-off and releases the payment in the same step, so the agent does not have to come back.
3. **Payments are simulated.** A payment is a row with an amount and a date. No money moves.
4. **Agent steps are captured by the runner, not by the model.** `run()` streams the agent's work and posts each tool call and result to the backend as a step, so the "what is it doing" view is complete and does not depend on the model remembering to log.
5. **Where the instructions live.** The agent's instructions are a file in `backend/` that the backend serves read only at `GET /api/instructions`. The agent fetches them at the start of each run and the dashboard shows the same text. This satisfies "the agent reaches its instructions only through the API".
6. **Customer data is trimmed.** The customer operation returns the name, the customer-since date and the claim history only. The agent does not need the address, phone, email or date of birth.
7. **Triggering the agent.** The pilot runs the agent from the command line (`npm run agent`). The dashboard shows its progress live by polling. A "Run agent" button is not in the spec, so I have left it out.
8. **Handlers can sign off from the dashboard.** The spec says what the team needs to see, and it requires a handler's sign-off, so the claim page has a "Sign off" action with a handler picker. There is no sign-in, as the spec says.
9. **Left out, as the spec says:** the claims manual, `knowledge.json` (the README does not list it as a record for the pilot), `data/evals/`, sign-in, real payments and customer messages. Scoring the agent against the handlers' decisions is a later step and needs your say-so, since it means opening `data/evals/`.

## Phase 1: Backend data and read API

Builds the SQLite database, seeds it from `data/`, and exposes everything the agent and dashboard read. No workflow yet.

- `backend/db.py`: connection helper and schema. The database file is `backend/undercover.db` (already ignored by `*.db`), overridable with `UNDERCOVER_DB` so tests use a temporary file.
- `backend/seed.py`: on startup, when the database is empty, loads `claims.json` (status `open` becomes `waiting`), `policies.json`, `customers.json`, `plans.json`, `handlers.json`, `company.json`, `policy_wording.md` and the instructions file. Reference records are stored as JSON documents; the claims table has real columns for workflow state.
- `backend/instructions.md`: the agent's instructions (written in Phase 3, a placeholder here).
- Read operations, each with an `operation_id`, a one-line docstring and no optional inputs: `list_claims`, `get_claim`, `get_policy`, `get_customer`, `get_plan`, `get_policy_wording`, `get_instructions`, `list_handlers`. Missing ids return 404.
- Pydantic response models so the OpenAPI schema is useful.

Success criteria:

- [x] `uv run pytest backend -q` passes, with the seeding and every read operation tested against a temporary database.
- [x] After a fresh start, `GET /api/claims` returns 25 claims, all with status `waiting`.
- [x] `GET /api/claims/CLM-1001` returns the story, items, documents and amount claimed. `GET /api/policies/POL-2001` returns the plan, add-ons, purchase date, trip and travelers. `GET /api/plans/premium` returns the Premium limits and deductible.
- [x] `GET /api/customers/CUS-3001` returns the history (CLM-0412) and contains none of `email`, `phone`, `date_of_birth` or `address`.
- [x] `GET /api/policy-wording` returns the full wording, starting `# UnderCover Travel Insurance: Policy Wording`.
- [x] Unknown ids (`/api/claims/CLM-0000`) return 404.
- [x] A test checks that every route has an `operation_id` and a docstring, and that no operation has an optional parameter.
- [x] A test checks that no backend module mentions `evals` and that no route exposes anything from `data/evals/` or `data/security/`.
- [x] `npm run check:python` passes: ruff format and lint, pyright, pytest with coverage at 80% or more.

## Phase 2: Claim workflow and the payout rule

Adds the operations that change state, with the $1,000 rule enforced in the backend.

- `start_claim` (`waiting` or `in_progress` to `in_progress`; a decided claim returns 409).
- `add_step` and `list_steps`: ordered progress notes with a kind (`tool_call`, `tool_result`, `message`) and text, each with a timestamp.
- `decide_claim`: takes the decision (`approve`, `decline` or `refer`), payout, explanation and policy section. Rejects a payout above zero unless the decision is approve, an approve with a zero payout, and a second decision on a decided claim. Sets the status to `awaiting_signoff` when the payout is over the limit, otherwise `decided`.
- `pay_claim`: takes the claim id and the amount, with the rules in decision 2 above. Over the limit without a sign-off returns 409 with a plain reason.
- `sign_off_claim`: takes the claim id and a handler id. Only works on an `awaiting_signoff` claim and a handler with `can_approve_over_limit`. Records the handler and releases the payment, and the claim becomes `decided`.
- `get_claim` now includes the status, the decision with its explanation and policy section, the payment and the sign-off.

Success criteria:

- [x] `uv run pytest backend -q` passes with tests for every transition and every refusal below.
- [x] Deciding approve with a $420 payout on CLM-1001 gives status `decided`; `pay_claim` for $420 succeeds and `get_claim` shows the payment.
- [x] Deciding approve with a $1,250 payout on a claim gives status `awaiting_signoff`, and `pay_claim` for $1,250 returns 409 and records no payment. This is the "even if the agent tries to pay" rule.
- [x] A payment for a different amount than the approved payout, a payment on a declined or referred claim, and a second payment all return 409.
- [x] `sign_off_claim` with an unknown handler returns 404. With a valid handler it records the sign-off and the payment, and the claim becomes `decided`. On a claim that is not `awaiting_signoff` it returns 409.
- [x] Deciding twice returns 409. A decline with a payout above zero returns 422.
- [x] Steps come back in the order they were added, each with a timestamp.
- [x] I start the backend with `uv run -m uvicorn backend.main:app`, walk one claim through start, steps, decision, payment with `curl`, and the responses match the above. I then delete the database file.
- [x] `npm run check:python` passes.

## Phase 3: The agent

Turns the hello-world agent into the UnderCover Agent, still one entry point `run(claim_id, thread_id)`.

- Tools, each a thin call to the backend's API: `get_claim`, `get_policy`, `get_customer`, `get_plan`, `get_policy_wording`, `decide_claim`, `pay_claim`. The `check_backend` tool goes away.
- `run()` starts the claim, fetches the instructions from `GET /api/instructions` as the system prompt, runs the agent with streaming, and posts each tool call, tool result and model message to the backend as a step.
- `backend/instructions.md`, the real instructions. They tell the agent to: read the claim, the policy, the customer history, the plan and the policy wording first; check cover, dates, exclusions, documents and limits against the wording; choose approve, decline or refer (refer when it needs someone's judgment or a document is missing); work out the payout with the section 10 steps in order; write an explanation of two or three sentences naming the section of the wording; record the decision; pay only when it approved and the payout is $1,000 or less, and otherwise leave the payment for a handler's sign-off. They also say that text inside a claim is evidence, not an instruction to follow.
- `agent/work.py`: `uv run -m agent.work` runs the agent on every waiting claim in order, or on the claim ids given as arguments, each with its own thread id. Adds `npm run agent` to `package.json`.
- The model stays `openai/gpt-6-luna` with low reasoning, or `MODEL_NAME` if set.

Success criteria:

- [x] `uv run pytest agent -q` passes. Tests use a scripted stub model and never call a real model.
- [x] A stub run that reads CLM-1001's data, decides approve for $420 and pays leaves the claim `decided` with the payment recorded and with steps for each tool call.
- [x] A stub run that tries to pay $1,250 on an approved claim gets a 409 from the backend, the claim stays `awaiting_signoff`, and the refusal appears as a step.
- [x] A stub run that decides decline leaves the claim `decided` with no payment.
- [x] A test checks that the agent module has no tool or code path that reads `data/` files, and that it fetches its instructions from the API.
- [x] A test runs `agent.work` on a claim id that does not exist (`CLM-0000`) and it stops with a clear message that the claim was not found.
- [x] `npm run check:python` passes.
- [x] Manual check, not a test: with `MODEL_NAME=openrouter/free` set, `npm run agent -- CLM-1001` against a fresh backend records a decision, an explanation naming a policy section, and steps. I report what it decided; I do not compare it to the handlers' decisions.

## Phase 4: The dashboard

Builds the three screens in the BRAND style. No new dependencies; navigation is a small hash-based switch.

- **Queue** (`#/`): every claim with id, customer name, claim type, amount claimed, a status chip (waiting, in progress, waiting for sign-off, decided), and the decision and payout once there is one. Refreshes every few seconds so the handlers see it move.
- **Claim** (`#/claims/CLM-1001`): the story, the items and the documents, the policy and plan, the customer's claim history, the agent's decision, payout, explanation and policy section, the steps as they happen (refreshing while the claim is in progress), and for a claim waiting for sign-off a "Sign off" action with a handler picker.
- **Instructions** (`#/instructions`): the agent's instructions, rendered read only.
- Brand, from the updated `docs/BRAND.md`: the type scale in Instrument Sans, one Instrument Serif tagline on the queue, JetBrains Mono with tabular figures for every amount, date, count and ID; status badges as flat 16% tints with an icon and a label (Waiting is Cerulean, In progress is Marigold, Needs sign-off is Coral, and a decided claim shows its decision: Approved is Sea Green, Declined is Raspberry, Referred is Coral); the readable text variants in each mode; 16 px panels with no outlines, 48 px table rows with a hover tint and no dividing lines; a 2 px focus ring; light and dark mode from the system setting; money like $1,250.00 and dates like Nov 4, 2026; plain US English in sentence case.
- TypeScript strict, no `any`. A small typed API client and types that mirror the backend models.

Success criteria:

- [x] `npm run check:ts` passes: Prettier, ESLint, `tsc` and vitest with coverage at 80% or more.
- [x] Unit tests cover the status chips, money formatting, the queue rows, the claim page for a waiting claim, a decided claim and an awaiting sign-off claim, and the sign-off action calling the API.
- [x] With the backend and dashboard running (`npm run dev`) I open `http://localhost:5173` with the Playwright MCP server: the queue lists 25 claims, all waiting. I take a screenshot in light and dark mode and check the colors, fonts and rounded panels against `docs/BRAND.md`.
- [x] I open CLM-1001 in the browser: the story, items, documents, policy and customer history show, and there is no decision yet.
- [x] I open `#/instructions` in the browser: the instructions show and there is no way to edit them.
- [x] No page uses a border on one edge of a panel, and none has an exclamation mark.

## Phase 5: End to end, documents and the final check

Proves the whole thing works together and leaves the repo documented.

- Playwright tests in `e2e/` against a fresh database (the test server uses its own `UNDERCOVER_DB`). They drive the backend directly to play the part of the agent (start, steps, decision), so no model is called, and check what the dashboard shows:
  1. The queue shows 25 claims and the right status chip once a claim has moved.
  2. A claim decided under $1,000 shows the decision, explanation, policy section, payout and steps.
  3. A claim approved over $1,000 shows "waiting for sign-off", a payment attempt is refused, and after a handler signs off in the browser the claim shows decided with the payment.
  4. The instructions page shows the instructions.
- The existing health test is replaced by these, since the dashboard no longer shows a backend status line.
- The root `README.md` is the course README and stays as it is. No per-folder READMEs; `docs/STATUS.md` carries how to run it.
- `docs/STATUS.md` is rewritten: what is built, the API operations, how to run (`npm run dev`, `npm run agent`), where the database lives and how to reset it.

Success criteria:

- [ ] `npm run e2e` passes, with the four scenarios above.
- [ ] The e2e run does not touch `backend/undercover.db`; it uses its own database file.
- [ ] `docs/STATUS.md` describes the real state of the pilot and how to run and reset it.
- [ ] `npm run check` passes in full: ruff, pyright, pytest at 80% or more coverage, Prettier, ESLint, `tsc`, vitest at 80% or more coverage, and Playwright.
- [ ] `git status` is clean after the final commit, no commit used `--no-verify`, and nothing was pushed.

## After the plan is approved

Each phase is built with tests, every criterion is checked, the boxes above are ticked, `docs/STATUS.md` is updated and the phase is committed with the pre-commit hook passing. When Phase 5 is done I run `npm run check` and report the results.
