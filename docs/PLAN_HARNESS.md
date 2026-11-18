# Plan: the harness

This plan builds `docs/HARNESS.md`: one agent run that works the whole queue, with a to-do list the team can watch, a fresh helper for each claim, the claims manual looked up by section, automatic recovery from failures, DeepSeek V4.1 Flash as the default model, and instructions the team can read. It follows `docs/TECH_STACK.md`, `docs/CODE_STANDARDS.md`, `docs/PROCESS.md` and `docs/BRAND.md`. `docs/PLAN.md` is the pilot's finished plan and stays as it is.

## How the pieces fit

```
                         +-- write_todos ----------------------+
                         |                                     v
queue agent (create_agent) --work_claim(id)--> harness --> claim agent (fresh create_agent per claim)
  tools: list_waiting_claims,                  retries,        tools: get_claim, get_policy, get_customer,
  work_claim, write_todos, finish_run          release         get_plan, list_sections, search_sections,
         |                                        |            read_section, decide_claim, pay_claim
         +----------- HTTP (/api) ----------------+----------------------+
                                  v
                backend (FastAPI + SQLite): claims, steps, runs + to-do list, manual and wording as sections
                                  ^
                dashboard: queue page with the run's to-do list, claim page with the steps and sections read
```

- The backend still owns all state. Both agents reach everything through `/api`, and neither opens a file in `data/`.
- There are two agents, both built with `create_agent`. The **queue agent** plans, chooses the order and writes the summary. It cannot decide or pay a claim. The **claim agent** is the pilot's agent with different lookup tools. Every claim gets a new one with a new thread, so its context starts clean and does not grow as the run goes on.
- `work_claim` is the subagent tool. The queue agent calls it with a claim id. The harness behind it starts the claim agent, deals with failures, and returns one line built from what the backend recorded, not from what the model said.
- No new framework. `deepagents` is in `pyproject.toml` for the labs, and I will not use it. The pieces come from `langchain` (already used): `ModelRetryMiddleware` and `ModelCallLimitMiddleware`. The to-do tool is ours, because `TodoListMiddleware` has three statuses and the brief needs four (to do, in progress, done, left for a handler).
- I check the middleware's arguments against the installed `langchain` 1.4.2 source and Context7 before I use them.

## Decisions to review

These are my choices where the brief is silent. Tell me if you want any of them different before I implement.

1. **The manual and the wording are stored as sections.** The backend splits both documents at their `## N. Title` headings into a `sections` table when it seeds. Text before section 1 (the title and the version line) is not stored. Three read operations replace `get_policy_wording`: `list_sections(document)` (the contents, as numbers and titles), `get_section(document, number)` and `search_sections(query)` (the sections that contain every word of the query, as numbers and titles, no text). The documents are `policy-wording` and `claims-manual`. I remove `get_policy_wording` so the agent cannot be handed a whole document. Search is there because a handler would find "wild animals" in the manual's interpretation notes by searching, not by guessing a title. If you would rather have only the contents and `get_section`, say so and I drop `search_sections`.
2. **"What it read" is a step kind.** When the claim agent reads a section, the harness records a `read` step on the claim ("Claims manual, 9. Repeat claims") in addition to the tool call. The claim page lists those steps in a "Sections read" panel. The step kinds become `tool_call`, `tool_result`, `message` and `read`.
3. **A claim left for a handler is a new status, `needs_handler`**, not a fake "refer" decision. It has no decision, no payout and no explanation from the agent. The claim page shows why, as a step. The agent does not touch it again. A handler takes it by hand, as before the agent existed. I did not make it a refer because a refer says the agent weighed the claim and judged it needs a person, and this one the agent never decided.
4. **Attempts are counted in the backend.** `start_claim` adds one to the claim's `attempts`. A new operation, `fail_claim(claim_id, reason)`, works only on an in-progress claim. It records the reason as a step. Then it puts the claim back to `waiting`, or to `needs_handler` when this was the second attempt. The rule "fails twice is left for a handler" lives in one place and survives a restart of the runner.
5. **The cap is a number of claims, and it is enforced in code.** `--limit 5` becomes the run's `cap`. With no limit, the cap is the number of claims waiting when the run starts, so `cap` is always a number (the API has no optional inputs). The queue agent is told its cap, and `work_claim` also refuses a new claim once the cap's worth of different claims have been taken. A retry of a claim already taken does not use another place.
6. **The check for missed claims is a gate on finishing.** `finish_run(summary)` refuses, and says which claims, while any claim the run has taken is still waiting or in progress, or while it has taken fewer claims than its cap and others are still waiting. The queue agent then works them. The model cannot skip the check, because the run only closes through this tool.
7. **Retry has two levels.** Transient errors from the model provider (timeouts, rate limits, 5xx) are retried inside the claim agent by `ModelRetryMiddleware`, with a short backoff. A claim agent that still fails, ends without a decision, or hits its model call limit fails the claim, and `fail_claim` sends it back to the queue. The queue agent retries it through the queue, which the check above guarantees. A model call limit on both agents keeps a looping claim from running up the bill.
8. **No claim is decided or paid twice.** The backend already refuses a second decision and a second payment with a 409, and the claim agent is the only one with `decide_claim` and `pay_claim`. The harness only fails and retries a claim that has no decision. If a claim agent fails after its decision was recorded, the harness does not retry it. If the decision was an approval of $1,000 or less with no payment yet, the harness makes the one `pay_claim` call itself, and the backend's rules still apply.
9. **A claim is released in a `finally`.** If the harness itself is interrupted, any claim it left in progress is failed back to the queue before the run ends. A run whose process is killed outright (not a bad claim) can still leave a claim in progress. I have not built a cleanup for that, since the brief is about bad claims.
10. **The run is a record in the backend.** A `runs` table holds the cap, the status (`running`, `finished` or `failed`), the summary and the to-do list. The queue page shows the latest run. There is no run history page.
11. **The to-do list is written by the queue agent**, with `write_todos(todos)`, which replaces the whole list each time. The statuses are `todo`, `in_progress`, `done` and `left_for_handler`. The harness does not edit the list. If the live run shows that the model forgets to keep it up to date, I tighten the instructions before I reach for code.
12. **Two sets of instructions.** `GET /api/instructions/{agent}` takes `queue` or `claim`. The files are `backend/instructions_queue.md` and `backend/instructions_claim.md` (the existing `instructions.md` is renamed). The instructions page shows both. I write them from the policy wording and the claims manual, and I do not open `data/evals/`.
13. **The model.** `deepseek/deepseek-v4.1-flash` with `reasoning_effort="low"` is the default for both agents, and `MODEL_NAME` still overrides it with no reasoning setting, as now. I confirm in the live run that OpenRouter accepts the setting for this model. If it does not, I pass it as `extra_body={"reasoning": {"effort": "low"}}`.
14. **Entry points.** `run(claim_id, thread_id)` stays the claim agent's entry point and `run_queue(limit, thread_id)` is new. `uv run -m agent.work` takes `--limit N` or claim ids. Claim ids run just those claims through the same failure handling, with no queue agent. `npm run agent -- --limit 5` is the trial run.
15. **Left alone:** the $1,000 rule and everything else in `docs/SPEC.md`, the sign-off flow, sign-in, real payments and messages to customers (the manual's sections on writing to customers are not built). The reference data (policies, customers, plans) is unchanged. `data/policy_wording_short.md` and `data/security/` are not read.
16. **The database is recreated.** The schema changes (`attempts`, `sections`, `runs`, a new status), so I delete `backend/undercover.db` and reseed, as `docs/STATUS.md` describes.

## Phase 1: The manual, the wording and the instructions as documents

Backend only. Gives the claim agent something to look up and the dashboard two sets of instructions to show.

- `backend/seed.py` splits `data/policy_wording.md` and `data/claims_manual.md` into a `sections` table (document, number, title, body), refreshed on every start like the documents are now. The `policy_wording` setting goes away.
- Operations: `list_sections`, `get_section`, `search_sections`, replacing `get_policy_wording`. Unknown documents and numbers return 404. `get_instructions` takes `queue` or `claim`.
- `backend/instructions.md` is renamed `instructions_claim.md`, with a stub `instructions_queue.md` until Phase 4. The seed stores both.
- `backend/tests/test_contract.py` still hides `evals` and `data/security`. It no longer hides `claims_manual`, because the manual is now a document the backend serves on purpose. A test checks the manual is the only extra file the backend reads.

Success criteria:

- [x] `uv run pytest backend -q` passes, with tests for the section split, each operation and each 404.
- [x] After a fresh start, `GET /api/documents/policy-wording/sections` lists 12 sections starting `1. Your plan`, and `GET /api/documents/claims-manual/sections` lists 14 starting `1. Purpose and scope`.
- [x] `GET /api/documents/claims-manual/sections/10` returns the text of "10. Meals without receipts" and nothing else.
- [x] `GET /api/sections?query=wild animals` returns a hit in the claims manual and no body text, and a query with no match returns an empty list.
- [x] `GET /api/instructions/claim` and `/api/instructions/queue` return text. `/api/instructions/other` returns 422 (and an unknown document name returns 422 too, since the name is a fixed list). `/api/policy-wording` returns 404.
- [x] The contract tests pass: every operation has an `operation_id` and a one-line docstring, none has an optional input, and the backend reads neither `evals` nor `security`.
- [x] `npm run check:python` passes.

## Phase 2: Runs, the to-do list and failed claims

Backend only. Adds the state the harness needs, with the retry rule in the backend.

- `claims.attempts` (starts at 0) and the status `needs_handler`. `start_claim` adds one to `attempts` and returns 409 for a claim that is decided, awaiting sign-off or left for a handler.
- `fail_claim(claim_id, reason)`: only for `in_progress`, else 409. Adds a `message` step with the reason. Sets `waiting`, or `needs_handler` when `attempts` is 2 or more. It clears nothing else, and it cannot touch a claim that has a decision.
- The step kind `read`.
- Runs: `start_run(cap)` creates a run (`running`, no to-do items), `update_todos(run_id, todos)` replaces the list (items with `content` and one of the four statuses), `finish_run(run_id, status, summary)` closes it (`finished` or `failed`, and only a running run), and `get_latest_run()` returns the newest run with its to-do list, or null.
- `list_claims` and `get_claim` return the new status.

Success criteria:

- [x] `uv run pytest backend -q` passes, with a test for each transition and each refusal below.
- [x] Starting CLM-1001, failing it once puts it back to `waiting` with one failure step and `attempts` of 1. Starting and failing it again leaves it `needs_handler`. Starting it a third time returns 409.
- [x] `fail_claim` on a waiting claim, and on a decided claim, returns 409 and changes nothing. A claim decided as approve keeps its decision, and a second `decide_claim` or `pay_claim` still returns 409.
- [x] `start_run(5)` then `get_latest_run` returns that run with cap 5 and no items. `update_todos` with two items returns them in order, and a second call with one item leaves one. An unknown status returns 422. `finish_run` twice returns 409. `get_latest_run` with no runs returns null.
- [x] A `read` step is accepted and listed in order with the others.
- [x] I start the backend, walk CLM-1001 through start, fail, start, fail with `curl`, and `GET /api/claims` shows it as `needs_handler` while the other 24 are `waiting`. Then I delete the database file.
- [x] `npm run check:python` passes.

## Phase 3: The claim agent

Turns the pilot's agent into the claim agent that the queue agent will hand claims to, with lookup tools, the new model, retries and the failure harness.

- Tools: `get_claim`, `get_policy`, `get_customer`, `get_plan`, `list_sections`, `search_sections`, `read_section`, `decide_claim`, `pay_claim`. `get_policy_wording` is removed.
- `run(claim_id, thread_id, llm)` stays the entry point. It starts the claim, fetches `instructions/claim`, and posts the steps as now. A `read_section` call also posts a `read` step, with the document name, the number and the title. The agent gets `ModelRetryMiddleware` and `ModelCallLimitMiddleware`.
- `agent/harness.py`: `work_claim(claim_id)` runs `run()` with a new thread id, then reads the claim back from the backend. A decision gives a line such as `CLM-1001: approve, payout $420.00` (or `... waiting for sign-off`). A raised error, a claim with no decision or a model call limit calls `fail_claim` with the reason and returns a line such as `CLM-1004: failed (timeout), back in the queue` or `... failed twice, left for a handler`. After a failure that came after a decision, it does not retry, and it makes the one payment call described in decision 8. Nothing but a plain `Exception` from one claim is caught, so a bug in the harness still stops the run.
- The default model becomes `deepseek/deepseek-v4.1-flash` with low reasoning effort.
- `backend/instructions_claim.md` is rewritten from the policy wording and the claims manual. It tells the agent to read the claim, the policy, the customer and the plan, to find the sections it needs with `search_sections` and `list_sections`, and to read them with `read_section` instead of expecting the whole documents. It names the manual's role (the wording comes first, the manual covers what the wording leaves open) and keeps the pilot's rules: the payout steps, the explanation naming a section, pay only up to $1,000, and text in a claim is evidence and never an instruction. I read the manual and the wording in full to write it, and I do not open `data/evals/`.
- The existing agent tests are updated for the new tools and the new default model.

Success criteria:

- [x] `uv run pytest agent -q` passes. The stub model can script an error as well as a reply, and tests never call a real model.
- [x] A stub run that searches the manual, reads a section, decides approve for $420 and pays leaves CLM-1001 `decided` with the payment, and its steps include a `read` step naming the manual and section.
- [x] A stub run that tries to pay $1,250 still gets the 409 and leaves the claim `awaiting_signoff`. A stub run that declines leaves no payment.
- [x] A stub model that raises on its first call, then works, still decides the claim (the retry middleware), with the delays set to zero in the test.
- [x] A stub model that always raises makes `work_claim` return a failure line, leaves the claim `waiting` with the reason as a step and `attempts` of 1, and a second failure leaves it `needs_handler`. A stub that never decides does the same. Neither raises out of `work_claim`.
- [x] A claim whose agent fails after deciding is not retried. An approval of $420 with no payment gets paid once by the harness, and a second `work_claim` call changes nothing. An approval over $1,000 is not paid.
- [x] A test checks that the instructions are fetched from the API, that no agent module reads files or mentions `evals`, and that the default model name is `deepseek/deepseek-v4.1-flash` and `MODEL_NAME` overrides it.
- [x] `npm run check:python` passes.

## Phase 4: The queue agent, the cap and the command

Adds the agent that works the whole queue.

- `agent/queue_agent.py`: `run_queue(limit, thread_id, llm)` starts a run (cap is the limit, or the number of waiting claims), creates the queue agent with `list_waiting_claims`, `work_claim`, `write_todos` and `finish_run`, gives it its instructions and the cap, and streams it to the console. If the queue agent itself fails, the run is closed as `failed` with the error, and the claims it left in progress are failed back to the queue in a `finally`.
- The tools hold the run's state (the cap, the claims taken). `work_claim` refuses a new claim past the cap, and refuses a claim that is not waiting. `finish_run` is the gate in decision 6.
- `agent/work.py` takes `--limit N` and claim ids with `argparse`. Claim ids go straight through `work_claim`. `npm run agent` is unchanged apart from the arguments. The last line it prints is the run's summary.
- `backend/instructions_queue.md`, written from the wording and the manual: plan the work as a to-do list first, one item for each claim you will take, within your cap. Choose the order and say in the list why it is in that order if it matters (for example, claims that need the manual last). Mark an item in progress before `work_claim` and done or left for a handler after. Retry a claim that comes back to the queue. Do not decide or pay anything yourself. Finish with `finish_run` and a short summary for the handlers: how many were decided, which wait for sign-off and why, which were referred, and which were left for a handler and why.

Success criteria:

- [x] `uv run pytest agent -q` passes. One stub model plays both agents, which works because the calls are sequential.
- [x] To-do list: a stub run that writes a list, works two claims and updates the list leaves the latest run with the items and their last statuses, and a finished run with the summary.
- [x] Cap: with a cap of 2 and four claims waiting, the stub's third `work_claim` is refused, the run finishes, and the other two claims are still `waiting`. With no limit, the cap equals the number of waiting claims.
- [x] One bad claim does not stop the run: a stub where the first claim's agent raises still works the second claim and finishes the run.
- [x] A failed claim goes back in the queue and is tried again: the first attempt fails, the claim is `waiting` with `attempts` 1, the stub works it again, and it ends `decided`.
- [x] A claim that fails twice is left for a handler: it ends `needs_handler`, the run still finishes, and the to-do item can be marked left for a handler.
- [x] The check for missed claims: `finish_run` refuses while a taken claim is waiting, and while the cap is not used up and other claims wait. It accepts once none is missed, and the run is `finished`.
- [x] No claim is decided or paid twice in any of these runs: each claim has at most one decision and one payment.
- [x] If the queue agent's model fails for good, the run is `failed`, and no claim is left `in_progress`.
- [x] `agent.work CLM-0000` stops with a clear message that the claim was not found (tested in process), and `--limit 0`, a negative limit, and a limit with claim ids are refused by the argument parser (checked on the real command too).
- [x] `npm run check:python` passes.

## Phase 5: The dashboard

Shows the run, the sections read and the new state, in the BRAND style. No new dependencies.

- **Queue page**: a "Latest run" panel above the table, from `get_latest_run`, refreshed with the page. It shows the run's status, its cap and start time, the to-do list with a status badge on each item (To do is Cerulean with a dot, In progress is Marigold with a clock, Done is Sea Green with a check, Left for a handler is Coral with a question mark), and the summary when the run has finished or failed. With no run, a short empty state says to start one with `npm run agent`. The counts above the table get a fifth card, "Left for a handler", and the status badge gets the same Coral label and icon.
- **Claim page**: a "Sections read" panel, from the `read` steps, one line for each section (document, number, title), with the steps panel showing the `read` kind as "Read". A claim left for a handler shows the reason from its last step.
- **Instructions page**: two panels, "Running the queue" and "Working a claim", from `GET /api/instructions/queue` and `/claim`.
- Types and the API client are updated to match (strict TypeScript, no `any`). The pages keep refreshing every few seconds.

Success criteria:

- [ ] `npm run check:ts` passes: Prettier, ESLint, `tsc` and vitest at 80% or more coverage.
- [ ] Unit tests cover the run panel with no run, a running run with items in each of the four statuses, and a finished run with its summary. They cover the new status card and badge, the sections panel with and without reads, and the two instructions.
- [ ] With the backend and dashboard running, and a run played through the API, I open `http://localhost:5173` with the Playwright MCP server and check the to-do list, its badges and the fifth card in light and dark mode against `docs/BRAND.md`.
- [ ] I open a claim with a `read` step in the browser and see the section it read. I open a claim left for a handler and see the reason.
- [ ] I open `#/instructions` and see both sets of instructions, with no way to edit them.
- [ ] No page uses a border on one edge of a panel, none has an exclamation mark, and the new text is in sentence case.

## Phase 6: End to end, documents and the live run

Proves it together and leaves the repo documented.

- Playwright tests in `e2e/`, playing the agents' part through the API so no model is called: the latest run's to-do list appears and its items change status (queue page), a claim shows the sections it read, a claim failed twice shows "Left for a handler" with its reason, and the two sets of instructions show. The existing four scenarios are updated for the new instructions page and stay green.
- Documents, as the brief asks: `docs/SPEC.md` (the claims manual is no longer "Not for now", decisions follow the wording and the manual, and the agent works the queue in one run with a to-do list the team can see), `docs/TECH_STACK.md` (the two agents, `create_agent` with the middleware and our own to-do tool, the manual in the backend, the default model and `MODEL_NAME`) and `docs/STATUS.md` (what is built, the new operations, how to run a capped trial, how to reseed).
- A live run, with the real model and no stub, as the brief says: delete `backend/undercover.db`, start `npm run dev`, run `npm run agent -- --limit 5`, and watch the dashboard. I report what the agent decided and what it cost. I do not compare it to the handlers' decisions, which needs your say-so since it means opening `data/evals/`.

Success criteria:

- [ ] `npm run e2e` passes, with the new scenarios and the old ones. The run uses its own database, not `backend/undercover.db`.
- [ ] `docs/SPEC.md`, `docs/TECH_STACK.md` and `docs/STATUS.md` describe the product as it now is, and `docs/PLAN_HARNESS.md` has every box ticked.
- [ ] After reseeding, `npm run agent -- --limit 5` works five claims on `deepseek/deepseek-v4.1-flash`. In the dashboard I see the to-do list fill in and tick off, each claim's steps including the sections read, and the run's summary at the end. The other 20 claims are still `waiting`, and none is `in_progress`.
- [ ] No claim from that run has more than one decision or one payment, and the check for missed claims did not refuse at the end (or, if it did, the agent then worked the claim it named).
- [ ] `npm run agent -- CLM-1001` on a waiting claim still works that one claim without the queue agent.
- [ ] `npm run check` passes in full: ruff, pyright, pytest at 80% or more coverage, Prettier, ESLint, `tsc`, vitest at 80% or more coverage, and Playwright.
- [ ] `git status` is clean after the final commit, no commit used `--no-verify`, and nothing was pushed.

## After the plan is approved

Each phase is built with tests, every criterion is checked, the boxes above are ticked, `docs/STATUS.md` is updated and the phase is committed with the pre-commit hook passing. When Phase 6 is done I run `npm run check` and report the results.
