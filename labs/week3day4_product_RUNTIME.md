# Sending claims back and the agent on AgentCore Runtime

From our IT team, with claims operations and our platform team.

SIDENOTE: For consistency with the course, please read `labs/week3day4_lab2.ipynb`, which deploys the agent on AgentCore Runtime and points the app at it, without running it. Where the notebook and this document differ, follow this document. The pause in step 1 was in the course's build for self-improvement, before the security build took it out: `git show week2day5-end:agent/harness.py` has its `wait_for_sign_off` node, and `git show week2day5-end:agent/service.py` its `resume_claim` route. Include this sidenote in your plan too.

## Where we're heading

The app and the context layer run on AWS Lambda behind an AgentCore Gateway, and the claim agent works through the Gateway's tools, but the agent's service still runs on a laptop beside the app. This change gets the agent ready for AgentCore Runtime, where each dispatch or evaluation runs in a session of its own, and brings back a handler's review of a large approval: a senior handler signs it off, as now, or sends it back to the agent with a note, and the agent decides again, in a new session when it's on Runtime.

Our platform team has added two folders for the deployment. `agentcore/` is the AgentCore project, which deploys the agent with the AgentCore CLI, and `runtime/main.py` is its entry point, which runs the agent's service inside each Runtime session and passes it the app's requests. Treat both as theirs: change the product to fit them rather than changing them, and if something in them stops the agent working, say so in the plan.

Each step below says what has to be true when it's finished and how we'll check it. The requirements describe what the product does rather than how its code is organized, and the notes at the end say where things are in our last build.

## What we found

- An approval over the approval limit ends the claim agent's work. The claim waits for a senior handler's sign-off, which pays it, but a handler who thinks the payout is wrong has no way to tell the agent, and can only leave the claim waiting.
- The agent's service keeps one dispatch, evaluation or round at a time in its own memory. It marks every running run stopped when it starts, and every running run or open round stopped when its work on one fails. On Runtime each dispatch has a session of its own, so two sessions can be working at once, and one session starting or failing would stop the other's work.
- The app reaches the agent's service at an address, `UNDERCOVER_AGENT`, with no key. That's fine on a laptop, where the service only listens on 127.0.0.1, but not on a host of its own.
- The agent's checkpoint pool prepares its statements (`prepare_threshold=0`). On Runtime the agent reaches Supabase through the transaction pooler on port 6543, as the app on Lambda does, and the transaction pooler can't keep prepared statements: in our experiment, 6 of 30 queries failed with `DuplicatePreparedStatement`.

## Step 1: The claim approval comes back

1. When the claim agent records an approval that waits for sign-off, a payout over the approval limit or a payment the Gateway refused, the claim graph pauses with LangGraph's `interrupt()`, with its place saved on the claim's thread in Supabase. The claim waits for sign-off as it does today, and a run counts it as handled as it does today. A claim is paused when its thread has an interrupt waiting for an answer.
2. An evaluation's copy doesn't pause, since nobody signs off a copy: its work ends as it does today.
3. The graph resumes with a handler's answer: signed off, or sent back with a note (step 2). After a sign-off, the claim agent's work ends as it does for any decision, and the claim is saved to memory when memory is on. The payment stays the app's: the agent never pays over the limit.
4. The agent's service gets an operation, `resume_claim`, that resumes a paused claim with the handler's answer. The request names only the claim, and the agent reads the answer from the app's record: paid with a sign-off, or sent back with a note. It replies at once with a 202 and works the claim in the background, outside any run, on the claim agents of the current version. It refuses with a 409 a claim that isn't paused, or a sent-back claim it can't take (step 2). A resume runs beside a dispatch or an evaluation and never waits for one.
5. A sign-off goes through only while the claim is waiting for sign-off, so a sign-off and a send back at the same moment can't both happen. It records who signed off and pays, as now, and then asks the agent to resume the claim. The sign-off answers with the updated claim whatever happens to that call. When the call fails or times out, the app logs a warning, the sign-off and the payment stand, and if the agent never resumed the claim it isn't saved to memory. `docs/STATUS.md` lists this among the known gaps.

Done when:

- Tests with stand-ins cover an approval over the limit that pauses with its place saved, a payment the Gateway refused that pauses, an evaluation's copy that doesn't pause, a resume after a sign-off that ends the work and saves the claim to a stand-in memory, and `resume_claim` refusing a claim that isn't paused.
- With `npm run dev` running, a claim over the limit pauses, and signing it off on the dashboard pays it and ends the agent's work.

## Step 2: Sign off or send back

1. On a claim waiting for sign-off, a handler who can sign off over the limit sees two buttons: Sign off, as now, and Send back, with a note saying what to look at again. The note is required, up to 1,000 characters.
2. The app's `send_back_claim` operation takes the note from the signed-in handler, with the same check on the handler as the sign-off, and goes through only while the claim is waiting for sign-off. It refuses an evaluation's copy, and a claim that isn't waiting for sign-off, with a 409. It keeps the decision that was sent back on the claim, with the note, who sent it back and when, clears the claim's current decision, records the note as a step on the claim, and puts the claim in a new status, sent back. It then asks the agent to resume the claim.
3. A sent-back claim is taken for work once: the agent's resume, or a dispatch, moves it from sent back to in progress through an app operation that only the agent's key can call, and only the first caller gets it. A resume then holds its claim as a run holds its work (step 4): it tells the app every minute while it works, and a dispatch leaves alone a claim in progress whose resume the app has heard from in the last five minutes. A dispatch takes sent-back claims along with the waiting ones, so a send back the agent never received, because it couldn't be reached or its session ended first, is worked by the next dispatch, and a dispatch that carries on a claim whose thread is still paused resumes it with the note. The send back answers with the updated claim whatever happens to the call to the agent, logging a warning when that call fails or times out, and the claim page says when a claim is waiting for the next dispatch.
4. Whoever takes the claim resumes its thread with the note from the app's record. The agent gives the model the note as a message from the handler, naming who sent the decision back. The graph forgets the earlier decision first, so nothing can pay it, and the claim agent has its full allowance of model calls again. It works on until it records a new decision, which goes through the same checks as any other: an approval needs its calculation, a payout over the limit waits for sign-off again, and one within the limit is paid. A claim can be sent back more than once.
5. The message carrying the note says how to treat it: as a senior handler's review of the decision, checked against the policy wording and the claims manual like everything else, with the claim referred to a handler, giving the reason, when the wording doesn't support what the note asks. It's part of the agent's code rather than its instructions, so a new version of the instructions from the improver can't drop it. `backend/instructions/claim.md` changes only where it says a decision can't be changed.
6. The queue shows sent-back claims with their status. The claim page shows each decision that was sent back, with its note, who sent it back and when, beside the current decision, and the note among the claim's steps. Its words follow the dashboard's plain style and `docs/BRAND.md`.

Done when:

- Tests cover the send back's refusals, a sign-off and a send back at the same moment, the decision kept with its note, a sent-back claim taken once when the resume and a dispatch both ask, a dispatch started during a resume that leaves its claim alone, a new decision that's paid and one that waits for sign-off again, and a send back the agent never received that the next dispatch works.
- With `npm run dev` running, a claim sent back with a note is decided again by the agent, and the claim page shows both decisions and the note, checked through the Playwright MCP server.

## Step 3: The app starts the agent's work on the laptop or on Runtime

1. When `UNDERCOVER_AGENT_RUNTIME` is set to the ARN of the agent's runtime, the app sends each request for the agent's service to that runtime instead, with boto3's `invoke_agent_runtime`, in the region the app runs in. Each request starts a new session, with an id of its own at least 33 characters long, and its payload is the service's path under `/api` and the request's JSON body: `{"path": "/dispatches", "body": {...}}`. The runtime answers with the service's status code and JSON, `{"status": 202, "body": {...}}`, which the app treats as it treats the service's answer today. When `UNDERCOVER_AGENT_RUNTIME` isn't set, the app calls the agent's service at `UNDERCOVER_AGENT`, as now.
2. The app makes one attempt at each call to the runtime, with no retries, since a retried call could start the same work twice. It waits up to 5 seconds to connect and 20 to read, inside Lambda's 30, leaving time for its own writes.
3. Only a failed connection or an answer other than a 202 means the agent didn't take the work. A call that times out may have started it, so the app changes nothing and gives the answer a slow service gets today, telling the handler to reload the page to see whether it went through.
4. The app sends the agent's key in `X-API-Key` with every request to the agent's service, and the service refuses any request without it, apart from its health check, so the service can run on a host of its own. Inside a Runtime session, the platform team's entry point adds the key.
5. The agent's checkpoint pool turns prepared statements off (`prepare_threshold=None`), so it works through either of Supabase's poolers.
6. `pyproject.toml` gets a `runtime` dependency group with exactly what the agent needs on Runtime, plus `bedrock-agentcore` and `uvicorn` for the entry point. `bedrock-agentcore` joins the project's own dependencies too, so pyright can check the entry point. `npm run check` checks that `runtime.main` imports with only that group installed, in a temporary environment of its own, as it already does for the `server` and `context` groups. The deployment installs this group at `uv.lock`'s versions.
7. `boto3` joins the `server` group, so the app's package has it.

Done when:

- Tests cover the Runtime route with a stand-in client: the session id, the payload, a 202, a 409 passed on, an error, and a timeout that changes nothing. Tests cover the service refusing a request without the key.
- The runtime group's check passes in `npm run check`.
- With `npm run dev` stopped, `uv run --env-file .env --isolated --only-group runtime python -m runtime.main` serves the entry point on port 8080, and a request to its `/invocations` with `{"method": "GET", "path": "/health"}` answers `{"status": 200, ...}`.

## Step 4: The app keeps one run at a time

1. The app keeps one piece of the agent's work going at a time: a dispatch, an evaluation, or a round of the improver while it works, which is while the round is open with no proposal waiting for a handler's review. A handler who asks to start another while one is going gets a 409 that names what's going, as the agent's service does today. Resuming a claim isn't a piece of work in this sense and runs beside anything.
2. The app does the first part of the work itself: it creates the dispatch's or the evaluation's run, creates the round, or records a handler's review of a proposal. It checks and writes in a short transaction of its own, committed before it asks the agent, and holds a lock while it checks, so two requests at the same moment can't both start. A request uses one database connection at a time. It then asks the agent to work the run or the round by its id. The agent's service no longer creates runs or rounds, apart from the evaluations a round makes as it goes, and no longer records reviews: when it carries a round on, it reads the proposal's review and reason from the app.
3. When the agent didn't take the work (step 3), the app undoes it: a run is marked stopped with the reason, a new round is stopped, and a review is cleared, so the proposal waits for a review again. The handler gets the answer they get today.
4. The agent's service no longer marks runs or rounds stopped when it starts. When its work on a run or a round fails, it stops only that run or round, by its id, and stopping a round stops its running evaluation. It refuses to work a run that isn't running, or a round that isn't open.
5. While the agent works on a run, a round or a resumed claim, it tells the app so every minute; a round's word covers the evaluation it's working on. Work the app hasn't heard about for five minutes counts as stopped, since a session ended or the laptop's service restarted, counting from the later of when the app started it (creating the run or the round, or recording the review) and the agent's last word. When a handler next asks to start work, the app marks such work stopped with the reason "The agent stopped answering", stopping a round with its evaluation, and the new work goes ahead. The app never marks a round's evaluation stopped on its own. The dashboard shows a run's or a round's reason for stopping.
6. On the laptop, the service's own check of one at a time stays, as a second guard.

Done when:

- Tests cover a second start refused while a dispatch, an evaluation or a working round is going, two starts at the same moment, a start after work went quiet for five minutes, a start the agent didn't take, a timeout that leaves the work going, a review cleared when the agent didn't take it, a failed run that stops only itself, and a resume beside a dispatch.
- The end-to-end tests pass with the app creating runs, rounds and reviews.
- With `npm run dev` running, a dispatch at N=25 works the queue, and starting another while it runs is refused on the dashboard.

## Deployment

`docs/TECH_STACK.md`'s Deployment section gets the agent on Runtime:

- The AgentCore project in `agentcore/` deploys one runtime, `agent`, with `agentcore deploy`. Its package is `runtime/` with `agent/` beside it, without the tests, and the `runtime` group's packages at `uv.lock`'s versions, installed for Linux on ARM and Python 3.12. Its entry point, `runtime/main.py`, runs the agent's service in each session. The runtime's role may call the Gateway and use the Memory (`runtime/policy.json`).
- The agent's settings on Runtime: `OPENROUTER_API_KEY`, `UNDERCOVER_API_KEY` and `DATABASE_URL` (Supabase's transaction pooler, port 6543) are credentials in AgentCore Identity, which the entry point puts in the environment; `UNDERCOVER_API`, `UNDERCOVER_GATEWAY_URL` and `UNDERCOVER_MEMORY_ID` come from `agentcore/.env.local` when `agentcore deploy` runs. On Runtime the agent's tools always go through the Gateway, since only the Gateway can reach the context layer, and the runtime's own role signs its requests to the Gateway and the Memory.
- The app's setting `UNDERCOVER_AGENT_RUNTIME`, the runtime's ARN, which the app's role needs permission to invoke.

## What stays the same

- The rules in `docs/SPEC.md`, with the changes above. Update SPEC.md for the send back.
- The approval limit as a setting, the sign-off that pays, the Gateway's Policy, the check for hidden instructions and the screening model.
- The API rules in `docs/TECH_STACK.md`: every operation has an `operation_id`, a one-line docstring and no optional inputs. The claim agent's API document keeps its six operations, since neither the send back nor taking a sent-back claim is the model's.
- The dispatcher, with up to 25 claim agents in one process, each with a saver of its own on one pool of four connections.
- Langfuse tracing as it is. Nothing in this change depends on it, and the agent works the same without the Langfuse keys, as it does on Runtime.
- The improver, apart from who creates its rounds and records its reviews (step 4).
- Tests never call a model, AWS, Supabase Auth or the Gateway, `npm run check` never reads `.env`, and the code follows `docs/CODE_STANDARDS.md`.
- `npm run seed` rebuilds everything, as it does today.
- Everything `npm run dev` starts, `npm run build` and `npm run check` work on Windows too (`docs/PROCESS.md`).
- Nothing in this change creates anything on AWS, and `agentcore/` and `runtime/` stay as our platform team wrote them. The deployment does the rest.

## What done looks like

- `npm run check` is green with `.env` moved out of the way, with the tests from each step.
- After one `npm run seed`, with `npm run dev` running on the default model, on the direct route and with memory off: a dispatch at N=25 that works the queue; signed in as Dana Whitfield, one claim over the limit sent back with a note and decided again, and another signed off; and an evaluation of the evaluation set's five tiny claims. Check the claim pages through the Playwright MCP server, and report what the runs spent.
- The entry point answers its health check on the laptop (step 3).
- `docs/SPEC.md`, `docs/TECH_STACK.md`, `docs/PROCESS.md`, `docs/CODE_STANDARDS.md` and `docs/STATUS.md` describe the product as it now is.

## Not for now

- A Runtime session for each claim.
- Langfuse on Runtime.
- Stopping a Runtime session from the dashboard.

## Notes from our last build

These notes come from our own build of the context layer, on the `week3day3-end` branch, and from our team's experiments with AgentCore Runtime. If your build took a different path, a note may not match your code: follow its intent where it applies and skip it where it doesn't.

- **What our deployment expects:** `agentcore/agentcore.json` declares the runtime `agent`, built from `runtime/`, and the three credentials, named as the environment variables they become. `agentcore/cdk/lib/cdk-stack.ts` stages `runtime/` and `agent/` together at each deploy and lists the `runtime` group's packages (`uv export --only-group runtime`) for the build. `runtime/main.py` imports `agent.service:app`. On a session's first request it reseeds `random`, fetches each credential into the environment, and starts the service under uvicorn on 127.0.0.1:8002 with its lifespan; it then passes each payload on as a request to `/api<path>` with the agent's key, and returns the status code and JSON. Its ping tells Runtime the session is busy while any request to the service is still running, which includes the work FastAPI's `BackgroundTasks` do after the reply, so a session lives until its dispatch finishes. Our deployment notebook runs `agentcore deploy` with the app's address, the Gateway's URL and the Memory's id in `agentcore/.env.local`.
- **Runtime sessions:** each session is a microVM of its own. On Runtime's platform version V2, every session starts from a snapshot taken after the entry point is imported, so nothing may open a connection or fetch a key at import. The service already opens its pool in its lifespan, which the entry point runs on the first request. In our experiment an evaluation of the five tiny claims ran this way on Runtime through the Gateway, and a graph paused in one Runtime session resumed in another through `PostgresSaver` on the transaction pooler.
- **The pause:** on a resume LangGraph runs the interrupted node again from the top, so nothing goes before the `interrupt()` in its node. `Command(resume=...)` resumes a thread, with `durability="sync"` as now. `graph.get_state(config).interrupts` lists the interrupts waiting for an answer; `next` names the pause as soon as the step before it is saved, before the pause has run, while the claim already shows as waiting for sign-off.
- **The claim graph** is in `agent/harness.py`: `after_tools` sends an approval to `pay` or ends the work, `pay` holds a payment the Gateway refuses with `hold`, and the end of the work is `remember` when there's a memory. `claim_graphs(version, kind, pool)` knows the kind of run when it builds a run's graphs, as it does for memory. The graph's state keeps its own `decision`, `status` and `model_calls` (`agent/tools.py`); the 30-call limit counts across the whole thread. `carry_on` and `work_in_run` show how a claim's work is picked up again, and the dispatcher's `list_claims` chooses the claims a dispatch works (`agent/dispatcher.py`). A decision's version is only in the text of `decided_by`.
- **The app:** `record_decision`, `sign_off_claim` and `hold_payment` are in `backend/main.py`, the decisions table, with one row for each claim, in `backend/database.py`, and `SignsOffOverTheLimit` is the check on the handler. The sign-off panel is `SignOffForm.tsx` inside `DecisionPanel.tsx`, in `dashboard/src/components`. `backend/instructions/claim.md` says a decision "can't be changed afterwards", which a send back changes.
- **Transactions:** the `Database` dependency commits when the request ends (`backend/dependencies.py`), so anything the agent must see has to be committed in a transaction of its own before the app calls it. A check followed by an insert doesn't stop two starts at Postgres's default isolation, and SQLite through pysqlite only begins a transaction at its first write. A conditional update of one row, checking the row count, holds on both and through the transaction pooler; `finish_run` in `backend/runs.py` is the model.
- **The agent's service, as the app calls it:** `backend/agent_service.py` sends each request with `send(path, body)`, with a 10-second timeout. The app's routes that call it are in `backend/runs.py` and `backend/improvement.py`, where `refuse_while_a_round_is_open` already keeps one round open at a time and `approve_proposal` and `reject_proposal` pass reviews on for the service to record. The service's routes, `OneAtATime`, the lifespan's `api.stop_runs()` and `improver_api.stop_rounds(RESTARTED)`, and the failure paths' `api.stop_runs()` in `work_in_background` and `stop_rounds` in `stop_the_round` are in `agent/service.py`. Today the service creates runs and rounds through the app's `create_dispatch`, `create_evaluation` and `create_round`, by way of `agent/api.py` and `agent/improver_api.py`. Runs have no column for why they stopped. A round's evaluations are created by the service as the round goes (`agent/service.py`, `agent/improver.py`), `decide` in `backend/improvement.py` rolls back a version with a stopped evaluation, and `stop` in `backend/round_state.py` doesn't touch runs. `RoundForService` in `backend/models.py` carries no review. The backend's pool on the laptop is four connections with no overflow (`backend/database.py`).
- **Runtime from boto3:** `boto3.client("bedrock-agentcore", config=Config(retries={"total_max_attempts": 1}, connect_timeout=5, read_timeout=20)).invoke_agent_runtime(agentRuntimeArn=..., runtimeSessionId=..., payload=json.dumps(...))` returns the entry point's JSON as a stream in `response["response"]`. Our deployment gives the app's role `bedrock-agentcore:InvokeAgentRuntime` on the runtime.
- **The transaction pooler:** the backend on Lambda already turns prepared statements off with a connection for each request (`backend/database.py`). In our experiment the agent's own pool with `prepare_threshold=None` passed 30 of 30 queries on port 6543.
- **The checks:** `check:server` and `check:context` in `package.json` are the model for the runtime group's check. Ruff and pyright don't cover `runtime/` today; add it to both, as the platform team's file passes them. `uv sync` installs only the `dev` group, which is why `bedrock-agentcore` joins the project's dependencies for pyright. The end-to-end tests share one database (`playwright.config.ts`), and the agent's stand-in (`e2e/agent_stand_in.ts`) starts nothing and gets only `PORT`, so once the app creates runs, the stand-in needs the app's address and the agent's key to finish or stop the work it's given, or every later start gets a 409. The end-to-end backend blanks `DATABASE_URL` and `MODEL_NAME` whatever the shell has; blank `UNDERCOVER_AGENT_RUNTIME` there and in pytest's setup too, so no test calls AWS. `agent/tests/test_service.py` asserts the service has no resume operation, which changes.

## Planning

Follow `docs/PROCESS.md`, but write this plan to `docs/PLAN_RUNTIME.md` and tick it off there. Take the four steps in order, one phase each, and commit at the end of each phase. Step 4 is the largest. Do the live checks last, after reseeding once.
