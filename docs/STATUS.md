# Status

The pilot from `docs/SPEC.md` is built, in the five phases of `docs/PLAN.md`.

## What is built

- `backend/`: FastAPI and SQLite. On startup it seeds the database from `data/` (claims, policies, customers, plans, handlers, the policy wording and the $1,000 approval limit). It never reads `data/evals/`, `data/security/` or the claims manual.
- `agent/`: the UnderCover Agent, `run(claim_id, thread_id)`. It starts the claim, fetches its instructions from `GET /api/instructions`, and works through tools that call only the backend's API. Each tool call, result and message is posted back as a step. `uv run -m agent.work` runs it over the queue.
- `dashboard/`: React, Vite and TypeScript, in the style of `docs/BRAND.md`, in light and dark mode. The queue (`#/`), a claim page (`#/claims/CLM-1001`) with the decision, reasons, agent steps and a sign-off action, and the agent's instructions, read only (`#/instructions`). Pages refresh every few seconds, so steps appear as the agent works.
- `e2e/`: Playwright tests of the queue, a claim under $1,000, a payout over $1,000 and the instructions page. They play the agent's part through the API, so no model is called.

## How a claim moves

`waiting`, then `in_progress` when the agent starts, then `decided`, or `awaiting_signoff` when it approves a payout over $1,000. `pay_claim` refuses with a 409 for such a payout until a handler signs off with `sign_off_claim`, which records the handler and releases the payment. Payments are simulated rows; no money moves.

## API operations

`health`, `list_claims`, `get_claim`, `start_claim`, `list_steps`, `add_step`, `decide_claim`, `pay_claim`, `sign_off_claim`, `get_policy`, `get_customer` (name and history only), `get_plan`, `get_policy_wording`, `get_instructions`, `list_handlers`. The OpenAPI schema is at `/docs` while the backend runs.

## Run

- `uv sync` and `npm install` once. Put `OPENROUTER_API_KEY` in `.env`.
- `npm run dev` starts the backend on port 8000 and the dashboard at http://localhost:5173.
- `npm run agent` works every waiting claim, and `npm run agent -- CLM-1001` works one. The backend must be running. Set `MODEL_NAME` (for example `openrouter/free`) to use another model than `openai/gpt-6-luna`.
- The database is `backend/undercover.db`, made on first start. Delete the file to reset the queue, which is also needed after a schema change. `UNDERCOVER_DB` points elsewhere.
- `npm run check` runs every check. The end-to-end tests use ports 8100 and 5273 and a temporary database, so they do not disturb a running `npm run dev`.

## Not built, as the spec says

The claims manual, sign-in, real payments, messages to customers, and scoring the agent against `data/evals/`.
