# Status

The pilot is being built in phases from `docs/PLAN.md`.

## Built

- Phase 1, backend data and read API. `backend/` seeds SQLite from `data/` on startup and serves read operations: `list_claims`, `get_claim`, `get_policy`, `get_customer` (name and history only), `get_plan`, `get_policy_wording`, `get_instructions`, `list_handlers`.
- Phase 2, claim workflow. `start_claim`, `list_steps`, `add_step`, `decide_claim`, `pay_claim` and `sign_off_claim`. A claim moves `waiting`, `in_progress`, then `awaiting_signoff` or `decided`. `pay_claim` returns 409 for a payout over the $1,000 limit until `sign_off_claim` records a handler, which also releases the payment. Payments are simulated rows.
- Phase 3, the agent. `agent/main.py` has `run(claim_id, thread_id)`: it starts the claim, fetches its instructions from `GET /api/instructions` (the file is `backend/instructions.md`), runs `create_agent` with tools that call only the backend API, and posts each tool call, tool result and message to the backend as a step. `uv run -m agent.work [CLAIM_ID ...]` (or `npm run agent -- CLM-1001`) works the given claims, or every waiting claim. The model is `openai/gpt-6-luna` unless `MODEL_NAME` is set.
- `dashboard/`, `e2e/`: still the hello-world page and test.

## Run

- `npm run dev` starts the backend on port 8000 and the dashboard on port 5173.
- The database is `backend/undercover.db`, made on first start. Delete the file to reset it, which is also needed after a schema change. `UNDERCOVER_DB` points elsewhere.
- `npm run agent` runs the agent over the waiting claims; the backend must be running.
- `npm run check` runs every check.
