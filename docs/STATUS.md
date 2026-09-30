# Status

The claims pilot in `docs/PLAN.md` and the harness in `docs/PLAN_HARNESS.md` are built: all six phases of each are done.

## Running it

- `npm run dev` starts the backend on port 8000 and the dashboard on http://localhost:5173.
- `uv run -m backend.seed` rebuilds the database from `data/`, putting every claim back in the queue.
- `uv run -m agent` works the whole queue with the queue agent. `uv run -m agent --cap 5` works at most five claims and leaves the rest waiting. `uv run -m agent CLM-1001` works one claim with the claim agent alone. Each prints a report line per claim, and a queue run ends with its summary. All use the real model through OpenRouter.

## Built

- `backend/`: SQLite database seeded from `data/` (never `data/evals/`), at `undercover.db` or the path in `UNDERCOVER_DB`, created on startup when missing. A test checks that every operation follows the API rules.
  - Read operations: `health`, `list_claims`, `get_claim`, `get_policy`, `get_claim_history`, `list_handlers`, `list_steps`, `get_instructions`, `search_documents`, `read_section`, `get_latest_run`.
  - Workflow operations: `start_claim`, `record_step`, `record_decision`, `pay_claim`, `sign_off_claim`, `fail_claim`, `start_run`, `write_todos`, `finish_run`.
  - Claims: a claim moves from waiting to in progress to decided, or to waiting for sign-off when an approval pays over the limit in `company.json`. `pay_claim` refuses such a payout with a 403 until a handler signs off, and signing off pays it. Each start counts as an attempt. `fail_claim` records the reason as an `error` step and puts the claim back to waiting, or after its second attempt leaves it `left_for_handler`.
  - Runs: a run has a cap, a to-do list that `write_todos` replaces whole, and a summary recorded by `finish_run`.
  - Documents: seeding stores the claims manual beside the policy wording, and the backend splits both into their numbered sections. `read_section` returns one section, and `search_documents` finds the sections that mention a word or phrase.
  - Instructions: `backend/instructions/queue.md` for running the queue and `claim.md` for working a claim, written from the policy wording and the claims manual. `get_instructions` serves both, with the claim instructions followed by the contents of the wording and the manual.
- `agent/`: the default model is `deepseek/deepseek-v4.1-flash` with low reasoning effort, a 120 second timeout and 5 retries, or the model in `MODEL_NAME`.
  - `work_claim(claim_id)` in `main.py` starts the claim with a new thread id and works it with a claim agent that has seven tools named after backend operations: `get_claim`, `get_policy`, `get_claim_history`, `search_documents`, `read_section`, `record_decision` and `pay_claim`. It records every tool call, tool result and message as a step, plus a `reading` step for each section read. A claim agent stops after 60 steps. Any failure, or finishing without a decision, is recorded with `fail_claim`, and a claim decided before a failure keeps its decision. It returns one line built from the backend's record, like `CLM-1001  approve  $420.00` or `CLM-1004  failed: ..., back in the queue`.
  - `run_queue(cap)` in `queue.py` first puts back any claim a stopped run left in progress. It then starts a run and a queue agent with `list_claims`, `write_todos` and `work_claim`. The queue agent chooses the claims and their order and keeps the to-do list. `work_claim` hands each claim to a new claim agent and refuses a new claim beyond the cap. When the queue agent tries to finish with claims missed within the cap, the harness names them, at most twice. Its last reply is recorded as the run's summary, and a failure of the queue agent finishes the run with the error.
- `dashboard/`: styled to `BRAND.md` in light and dark mode. The queue and a claim page refresh every two seconds.
  - The queue (`/`): counts by state, the latest run with its to-do list and summary, and a line per claim. Claim ids in the to-do list link to the claim.
  - A claim (`/claims/:claimId`): its policy, earlier claims, the decision and payment, the sections the agent read, the agent's steps as it works, including failed attempts, and a sign-off form for a held payout. It says when a claim is back in the queue after a failed attempt or left for a handler.
  - The agent's instructions (`/instructions`): for running the queue and for working a claim, read only.
- `e2e/`: tests of the three pages, the agent's steps appearing on a claim page, a handler signing off a held payout, the to-do list being ticked off on the queue, and a claim that fails twice being left for a handler. Playwright runs its own backend on port 8001 with `e2e/undercover.db`, and its own dashboard on port 5174, so it can run next to `npm run dev`.

## Last live run

On September 29, 2026, after reseeding, `uv run -m agent --cap 5` with `deepseek/deepseek-v4.1-flash` worked five claims, oldest submitted first, in 2 minutes 20 seconds: CLM-1001 approved and paid $420.00, CLM-1008 approved for $2,240.00 and CLM-1011 for $1,150.00, both waiting for sign-off, CLM-1018 referred and CLM-1010 declined. No claim failed, and the other 20 stayed waiting. Each claim agent read 9 to 11 sections, 5 or 6 of them from the manual. These decisions have not yet been scored against the handlers' decisions in `data/evals/`.

For the pilot, on September 27, 2026, `uv run -m agent` with `openai/gpt-6-luna` worked all 25 claims in 2 minutes 47 seconds: 17 approve, 5 decline and 3 refer.
