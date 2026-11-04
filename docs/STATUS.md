# Status

The pilot is being built in phases from `docs/PLAN.md`.

## Built

- Phase 1, backend data and read API. `backend/` seeds SQLite from `data/` on startup and serves read operations: `list_claims`, `get_claim`, `get_policy`, `get_customer` (name and history only), `get_plan`, `get_policy_wording`, `get_instructions`, `list_handlers`.
- `agent/`: still the hello-world entry point `run(claim_id, thread_id)`.
- `dashboard/`, `e2e/`: still the hello-world page and test.

## Run

- `npm run dev` starts the backend on port 8000 and the dashboard on port 5173.
- The database is `backend/undercover.db`, made on first start. Delete the file to reset it. `UNDERCOVER_DB` points elsewhere.
- `npm run check` runs every check.
