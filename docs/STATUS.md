# Status

The claims pilot is being built to `docs/PLAN.md`. Phases 1 to 4 of 6 are done.

## Built

- `backend/`: SQLite database seeded from `data/` (never `data/evals/`), at `undercover.db` or the path in `UNDERCOVER_DB`. It's created on startup when missing, and `uv run -m backend.seed` rebuilds it. Read operations: `health`, `list_claims`, `get_claim`, `get_policy`, `get_claim_history`, `list_handlers`, `list_steps`. Workflow operations: `start_claim`, `record_step`, `record_decision`, `pay_claim`, `sign_off_claim`. A claim moves from waiting to in progress to decided, or to waiting for sign-off when an approval pays over the limit in `company.json`. `pay_claim` refuses such a payout with a 403 until a handler signs off, and signing off pays it. `get_instructions` serves the agent's instructions from `backend/instructions.md`, followed by the policy wording. A test checks that every operation follows the API rules.
- `agent/`: `run(claim_id, thread_id)` starts the claim, fetches its instructions from the backend and works the claim with five tools named after backend operations: `get_claim`, `get_policy`, `get_claim_history`, `record_decision` and `pay_claim`. It records every tool call, tool result and message as a step. `uv run -m agent CLM-1001` works one claim with the real model.
- `dashboard/`: React Router pages for the queue (`/`), with counts by state and a line per claim, a claim in full (`/claims/:claimId`), with its policy and earlier claims, and the agent's instructions (`/instructions`), read only. The queue and a claim page refresh every two seconds. Styled to `BRAND.md` in light and dark mode.
- `e2e/`: tests of the three pages. Playwright runs its own backend on port 8001 with `e2e/undercover.db`, and its own dashboard on port 5174, so it can run next to `npm run dev`.
