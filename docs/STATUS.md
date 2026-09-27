# Status

The claims pilot is being built to `docs/PLAN.md`. Phase 1 of 6 is done.

## Built

- `backend/`: SQLite database seeded from `data/` (never `data/evals/`), at `undercover.db` or the path in `UNDERCOVER_DB`. It's created on startup when missing, and `uv run -m backend.seed` rebuilds it. Read operations: `health`, `list_claims`, `get_claim`, `get_policy`, `get_claim_history`. A test checks that every operation follows the API rules.
- `agent/`: the hello-world entry point `run(claim_id, thread_id)`, with one tool that calls the health route
- `dashboard/`: one page that shows whether the backend is up
- `e2e/`: one test of that page. Playwright runs its own backend on port 8001 with `e2e/undercover.db`, and its own dashboard on port 5174, so it can run next to `npm run dev`.
