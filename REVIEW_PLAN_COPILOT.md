# Review of the Copilot implementation plan

Reviewed `docs/PLAN_COPILOT.md` against `docs/COPILOT.md`, the project's required guidance, the existing backend, agent and dashboard, the referenced deployment material, and the installed framework code.

**Recommendation: revise the plan before implementation.** The overall architecture and six-phase structure are sound. The most serious gaps concern what a confirmation authorizes, recovery when a turn stops, the correctness of the success-criteria answer, and keeping the handler's token out of SDK logs. Several success criteria currently miss these cases; one explicitly requires incorrect behavior.

This is a review of the proposed design, not a claim that these bugs already exist in an implemented Copilot. Plan line references below refer to the version reviewed. P1 findings should be resolved before building the affected phases; P2 findings need explicit implementation decisions and acceptance tests.

## What the plan gets right

- It follows the required hand-written `StateGraph`, `ToolNode`, separate interrupt node, synchronous execution and durable checkpointer. It reproduces the course sidenote and uses the deployment notebook's runtime, environment and memory names.
- The handler's token belongs in runtime context, and the separate `call_as` path avoids the claim agent's API key. Checking `/api/me` before model work and enforcing conversation ownership in the backend are the right boundaries.
- Sign-off remains a handler operation enforced by the backend. Confirmation details come from records, and a fresh process can resume the graph.
- Waiting happens in code against the specific run returned by a start. The dedicated success-criteria tool and backend payment count provide a good basis for deterministic reporting.
- The proposed reads avoid the answer key. In today's code, `get_run` returns agent outcomes and `list_evaluations` returns aggregate measures; `get_evaluation` adds handler decisions. Keeping the latter out of the Copilot's API is appropriate.
- Handler memory has its own store setting and namespaces, derives its actor from verified identity, and saves only the user message and final answer.
- The plan covers the sidebar, ownership, token refresh, model-call limits, optional memory, local and Runtime entry points, and the required handover. It does not add AWS provisioning to application code.

## Findings to resolve before implementation

### 1. P1 — The success-criteria answer deliberately preserves invented figures

**Plan:** lines 94, 128–139 and, most clearly, the phase 3 test at line 317. **Spec:** `docs/COPILOT.md:104`.

The plan appends the correct table to unrestricted model text. Its test explicitly preserves “We're at 50% straight through and 40% accurate” before a table reporting 80% and 88%, then saves that contradictory answer to memory. That directly violates the requirement that every figure in this answer come from records and be worked out in code. A prompt asking the model not to repeat figures does not enforce it. The model can also falsely say “All three are met” before a table showing a failure.

**Change:** make the published success-criteria result authoritative in code, including its overall verdict and unavailable-results explanation. A deterministic answer is the simplest option; if model commentary is retained, define a constrained output contract that cannot introduce alternative figures or a contradictory verdict. Use the same final answer for the sidebar, conversation history and memory. Do not rely on simply removing digits: an incorrect claim can use words.

**Acceptance:** replace line 317 with tests that supply contradictory figures and verdicts from the stub and verify that neither is published or remembered. Test exact threshold equality, a failed criterion, and unavailable evaluation results; unavailable must not be presented as a failed measurement or as “all three met.”

### 2. P1 — A confirmation is not bound to the decision and amount the handler saw

**Plan:** lines 90–92 and 108–113. **Existing code:** `backend/main.py:518` and `backend/main.py:533`.

The card is a snapshot, but the eventual sign-off calls the existing operation using only `claim_id`. While the card waits, another tab or handler can send that decision back, and the claim agent can record a different held payout. The old card might show $1,350 while the current decision asks for $3,750. The existing endpoint signs off the current held decision; it has no knowledge of the snapshot the user confirmed. This is especially relevant because the spec permits answering on another day.

Re-reading the claim before sending the sign-off is insufficient by itself: the decision can change between the read and the payment transaction. The plan's “already signed off by this handler counts as done” rule is also too broad to establish that this particular confirmation succeeded.

**Change:** assign the held decision a stable revision or equivalent immutable identity, record it with the confirmation, and check that identity atomically in the backend transaction that pays. Reuse the existing sign-off business logic through an explicit confirmation-aware path or a carefully designed precondition. A changed decision must require a fresh card and a fresh click. Record a receipt tied to the confirmation so a replay can identify its own completed payment.

**Acceptance:** pause, send back, record a different held decision, and answer the old card: no payment. Repeat with the same amount but a different decision/reason. Test a change concurrent with sign-off, an already-paid claim, and an exact replay after payment committed but the response was lost.

### 3. P1 — An old browser tab can answer a different confirmation

**Plan:** line 160, `POST /api/copilot/conversations/{conversation_id}/confirmation`, body `{answer}`.

The request identifies the conversation but not the card. Suppose tab A shows confirmation X. In tab B the handler cancels X and later receives confirmation Y in the same conversation. Clicking the old button in A sends the same request that would approve Y. The backend's “something is waiting” check and the Copilot's “latest working turn” check both accept the newer turn.

**Change:** require the displayed `turn_id` and a unique confirmation identifier, and condition the transition on that exact pending confirmation. Associate the saved LangGraph interrupt with it too. Duplicate answers and callbacks must either return the recorded outcome for that identifier or refuse without touching a newer card. Define whether a turn can contain multiple sequential confirmations; a single reusable `confirmation_answer` cannot safely stand for all of them.

**Acceptance:** exercise two tabs, a stale answer after cancellation, a stale answer after a new turn, and simultaneous Sign off/Cancel requests. Only the card actually displayed and selected may be answered.

### 4. P1 — A turn being displayed as stopped does not stop its worker or protect the next turn

**Plan:** lines 149–151, the entrypoint's process-local guard, and phase 4 line 338.

After 20 minutes the backend accepts a new message, but the old thread may still be running. In the same process, the proposed conversation guard refuses the new work, contradicting the requirement that the handler can continue after a stopped turn. In a different process there is no such guard: both workers can write to the same checkpoint thread. Rejecting late sidebar records does not protect an action already past its card-start check or prevent another graph checkpoint from the old worker.

There is also no persisted stopped status in the proposed table. Unless every transition uses the same effective-status/deadline condition, a late `finish_turn` can turn a previously displayed stopped turn into done.

**Change:** define a backend-authoritative execution generation/claim and a terminal transition for expired work. Specify how an old worker loses permission to proceed, how a successor starts without competing checkpoint writers, and how action calls and final callbacks are tied to the current execution. Check before further model/tool work, including after a long wait. A stale worker must not block a valid successor indefinitely. This is recovery ownership, not a new user-facing stop feature.

**Acceptance:** hold a worker inside a tool past the deadline, start the next turn, then release the old worker. Run both in one process and with separate app instances sharing the saver. The new turn must proceed; the old worker must not overwrite its state, publish an answer, or start another action.

### 5. P1 — Application records and graph checkpoints can disagree after a crash

**Plan:** lines 95–97 and 110–112; `turns.py` reports a pause or completion only after running the graph.

There are two independent durable stores: the LangGraph checkpoint and the backend's turn/card records. The plan describes the normal order but not recovery at the boundaries. Examples include:

- The interrupt is saved, but the process dies before `pause_turn`: the app shows working and eventually stopped, with no confirmation card.
- The app accepts a confirmation and the graph consumes it, but the process dies before reporting the result: the app shows working even though the graph no longer has an interrupt.
- The answer and memory save complete, but `finish_turn` never reaches the app: the conversation state contains an answer the sidebar never shows.

Closing dangling tool calls on the next message does not reconcile these states. A blanket “step stopped before it finished” can also be false if the action committed and only its response or card update was lost.

**Change:** define an explicit reconciliation table for app status, graph status and recorded action outcomes. Make pause/finish callbacks safely repeatable for the same turn and confirmation. On an authorized reload/continuation, recover a saved pause or final answer when possible, and distinguish an unknown action outcome from an action known not to have happened. Never infer a successful payment solely from the stored button answer.

**Acceptance:** inject failures immediately before and after each checkpoint, pause report, confirmation transition, payment response, memory save and finish report. Rebuild the Copilot on the same saver and verify the sidebar, graph and backend agree, without duplicate effects. The existing fresh-process pause test covers only the successful boundary.

### 6. P1 — Non-payment actions have no durable identity for ambiguous outcomes

**Plan:** `cards.py`, lines 92 and 117–128, and the step schema at line 147. **Existing code:** `backend/runs.py:489` and `backend/main.py:533`.

Dispatch starts, evaluation starts and send-backs can commit before a connection drops or a checkpoint is saved. None is currently identified by a Copilot action/turn receipt. A repeated start after the first run finishes can create a second run; a repeated send-back can affect a newly held decision. The success-criteria tool also performs start, wait and measurement inside one tool invocation, leaving no specified durable run reference until the invocation completes.

Synchronous checkpointing protects completed graph steps, not an external mutation and its following checkpoint as one transaction. LangGraph's guidance likewise requires side effects to be designed for re-execution; a checkpointer alone does not supply an exactly-once API. See [LangGraph interrupts and side effects](https://docs.langchain.com/oss/python/langgraph/interrupts#side-effects-called-before-interrupt-must-be-idempotent).

**Change:** record an action identifier, its intended target/revision, and its result such as `run_id`, with a uniqueness rule enforced where the action commits. Preserve the started evaluation's identity before entering its long wait. On uncertain responses, reconcile the same action rather than asking the model to repeat it without context. Keep card identity stable across retries as well.

**Acceptance:** let a start/send-back commit and then drop its response or fail its card update. Continue the conversation and verify there is one run or send-back, the recorded outcome is recovered, and a later decision cannot be affected by the old request.

### 7. P1 — Token-free application logs do not guarantee token-free SDK logs

**Plan:** lines 102–105, Runtime payloads, and the DEBUG-log assertions in phases 1 and 4.

The handler token is included in the JSON body passed to boto3. The installed `botocore.endpoint.Endpoint.make_request` logs the request parameters, including that body, at DEBUG. I verified this locally with fake credentials, a fake token and the network send replaced: the fake token appeared in captured botocore DEBUG logs. No live service or real credential was involved.

A stand-in that replaces `invoke_agent_runtime` never exercises that logging path, so the planned test can pass despite the leak. Formatting the application's own errors without values does not fix SDK logging. SDK exceptions and chained validation errors also deserve inspection because the plan persists short exception descriptions.

**Change:** specify protection at the logging boundary for token-bearing requests, including third-party request logging and exception formatting. Avoid process-global per-request token filters that could mix handlers or leave gaps under concurrency. Keep safe diagnostic metadata without payloads or authorization headers.

**Acceptance:** exercise the real boto3 serialization/request path with fake credentials and a stubbed network boundary while capturing DEBUG output. Include malformed payloads, refusals, timeouts and concurrent handlers; inspect exception logs, checkpoint writes and saved failure/card text as well as application log messages.

### 8. P1 — The over-limit criterion changes the definition in the brief

**Plan:** line 138. **Spec:** `docs/COPILOT.md:100–104`. **Existing code:** `backend/main.py:429` and `backend/main.py:475`.

The brief asks whether queue payments over the approval limit have a handler's sign-off. The plan instead compares each payment with the limit stored when its decision was recorded. Those are different measures when Settings changes. For example, a $900 automatic payment made under a $1,000 limit is excluded by the plan even if today's limit is $500. Conversely, a signed $1,350 payment is counted by the plan after the limit rises to $2,000, although it is no longer above the current limit.

Historical compliance might be a useful separate measure, but the plan should not silently substitute it for the requested current-limit check. The system already distinguishes the limit at decision time from the current payment limit, so tests with unchanged settings cannot expose this discrepancy.

**Change:** use the Settings limit for the specified criterion, or explicitly resolve the business definition in the spec before implementation. Return the limit used alongside both counts from one consistent read, so the answer can explain the scope. Likewise identify when the accuracy objective is sampled if it changes during the evaluation.

**Acceptance:** test a raised limit, a lowered limit, payment exactly at the limit, no qualifying payments, exclusion of evaluation copies, and a deliberately seeded payment lacking sign-off. The last case proves the criterion can actually report No; the planned tests demonstrate only successful and empty counts.

## Further implementation risks

### 9. P2 — Permission checks are inconsistent across the two senior-handler actions

**Plan:** phase 2 line 292 versus lines 90 and 296. **Spec:** item 2 says the Copilot knows permissions and tells an unauthorized handler rather than trying the action.

Sign-off is refused locally before an action call, but the send-back test relies on calling the backend and displaying its refusal. Marcus cannot send a held decision back either: today's route uses the `SendsBack` senior-handler dependency.

**Change:** apply the verified handler permission check consistently to send-back and sign-off, while retaining backend enforcement. Test that neither mutation endpoint is called for Marcus, and that permissions changed since an earlier turn are checked again. Include tests that unsupported actions such as changing Settings or starting an improvement round produce directions to the dashboard and no mutation.

### 10. P2 — Serial tool execution is not enforced by disabling parallel model calls

**Plan:** lines 88–90 and the `ToolNode` design.

The plan requests `parallel_tool_calls=False` and handles a sign-off beside another tool, but does not define what happens to multiple ordinary tools or multiple sign-offs in one model response. The installed `ToolNode` uses an executor for the supplied calls; the claim harness separately limits concurrency. Model settings alone should not determine the ordering of mutations and confirmations.

**Change:** choose and enforce one code-level rule: serialize the calls, or refuse additional calls with a `ToolMessage` for every rejected call id. Cover the special sign-off schema's validation too, since it bypasses the ordinary tool node. Preserve `Command` state updates from the criteria tool through the card wrapper.

**Acceptance:** return two mutations, two sign-offs, a sign-off plus a lookup, malformed arguments, and an unknown tool from the stub. Verify ordering, complete tool-call responses, at most the intended mutation, and no accidental concurrent payments or lost criteria state.

### 11. P2 — The invocation retries lack a total budget for the deployed Lambda

**Plan:** Runtime transport table and four attempts with 1/2/4-second waits. **Deployment:** `labs/week3day4_aws.py:145–149` sets the backend Lambda timeout to 30 seconds.

Each attempt can consume 5 seconds connecting and 20 reading. A conflict is safe to retry, but it can arrive after some latency, so four attempts plus waits do not have a 30-second upper bound. Local tests shortening sleeps do not verify the deployed behavior. The callback chain also holds a backend database connection while the Copilot calls the app back for `/api/me` and the conversation; this extends an existing connection-pressure risk documented in `docs/STATUS.md`.

**Change:** use a total invocation deadline that leaves time to return or record the outcome within the existing Lambda budget, and cap each retry to the remaining time. Preserve the distinction between a request known not to have reached the worker and one with an uncertain result. Review releasing the request's database connection before the service call without losing transactional guarantees.

**Acceptance:** simulate late conflicts, a cold start and a timeout after acceptance. Verify elapsed bounds and correct turn state. Exercise several simultaneous conversation starts with the backend's connection limit and callbacks enabled.

### 12. P2 — The extra runtime changes the database connection budget

**Plan:** shared `open_checkpoint_pool()` unchanged and one Runtime session per conversation. **Existing code:** `agent/harness.py:122`; **operational evidence:** `docs/STATUS.md`'s connection measurements.

The current checkpoint pool has a minimum of one connection and a maximum of four per process. On the laptop, adding a Copilot process means another pool alongside the backend and claim agent. On Runtime, separate conversations create separate processes and pools. The existing measurements already report 8–9 connections against a documented allowance of 12; simply keeping “four per process” does not establish that the new total is acceptable.

**Change:** state the expected number of active conversations/sessions, allocate pools for that workload, and include the resulting total in the live checks. Verify that setup on a new session is safe when both runtimes initialize their checkpoint tables concurrently. Reuse the transaction-pooler settings and avoid holding a checkpoint connection during the 15-minute wait.

**Acceptance:** measure connection use during a Copilot turn that starts a dispatch, while another handler has a conversation. Add local tests for pool exhaustion/setup failure and recovery; live database checks can remain in the final phase.

### 13. P2 — Confirmation outcomes and elapsed time need more than one answer flag

**Plan:** lines 113, 146 and 149; phase 5's “Signed off and paid” test.

Choosing Sign off is an authorization, not evidence that payment succeeded. The backend can refuse, the sign-in can expire, or the response can be lost. A turn can also pay successfully and then fail during a later model call. The proposed schema does not explicitly distinguish these outcomes. A single `paused_at`/`answered_at` pair also cannot account for several sequential confirmations in one turn without overwriting earlier waiting time and card history.

**Change:** represent each confirmation's requested answer separately from its action outcome and payment receipt. Render “Signed off and paid” only from a confirmed backend result. Either support a sequence of confirmation records and accumulated active time, or define a deliberate single-confirmation-per-turn restriction. Handle a refused/failed sign-off through the same model-visible refusal and card rules as other actions.

**Acceptance:** confirm after the claim was paid elsewhere, after permissions were revoked, and with an expired token; simulate a payment success followed by an answer failure. Verify the card reports the actual payment result. Test two pauses if supported and ensure waiting time is excluded from the whole turn's duration.

### 14. P2 — The phase gates contradict the proposed refactor

**Plan:** phase 2 lines 303–305, and phase 3 line 311. **Existing tests:** `agent/tests/test_boundaries.py`, especially `test_the_routes_and_who_uses_them` and `test_the_memory_uses_nothing_else_in_the_agent_and_the_claim_agent_uses_it`.

Phase 2 requires the tools to equal the final table even though phase 3 adds several of those tools. It also requires the claim agent's tests to pass unchanged, while existing boundary tests explicitly require `harness` to import `gateway`/`direct` and `memory` to import no other agent module. The proposed extraction intentionally changes both relationships. Those assertions must change to test the new design; leaving them untouched cannot satisfy the phase.

The proposed boundary list also bans direct `connection` imports outside `app_api.py`, but `turns.py` and the graph must recognize refusals. Decide whether the API module exposes the expected refusal contract or a neutral shared errors module owns it, rather than discovering this while implementing.

**Change:** make tool inventories phase-specific and list necessary structural-test updates explicitly. Preserve the claim agent's behavioral regression coverage while rewriting architecture assertions around the shared modules. Resolve the `ToolRuntime`/context protocol experiment early, with the installed version, before committing to the full extraction.

**Acceptance:** the new boundary tests must detect forbidden dependencies while allowing the intended ones. Existing claim behavior, Gateway refusals, memory isolation, resumption and API-key behavior must remain covered and pass.

## Additional acceptance criteria and clarifications

These are useful additions to the relevant phases, rather than reasons to expand the product's scope:

| Area | Add or clarify |
| --- | --- |
| Authentication isolation | Run Dana and Marcus turns concurrently through the shared HTTP client. Assert request-local bearer headers, no retained default authorization, no agent key, and no cross-handler memory or conversation content. Test refresh failure as well as 19/21-minute expiry boundaries. |
| Answer-key isolation | Assert the actual response/tool payloads contain no labeled handler decisions or reasons. A grep for `get_evaluation` is a useful boundary check but is not a data-isolation test. Keep the Gateway's six-operation app schema unchanged. |
| Context trust | State that customer stories, tool results and recalled preferences are evidence, not authority to start actions or override confirmation. Test a claim document that instructs the Copilot to pay/send back. Do not add a new screening model merely to address this. |
| Tool cards | Specify stable ordering, idempotent completion and terminal treatment of cards left working by a failed/stopped turn. Never present an uncertain committed action as definitely refused. Keep display truncation separate from the full tool result needed by the model. |
| Waits | Use a monotonic deadline including HTTP time, not just a number of sleeps. Give a link and identify the started run on timeout. For criteria, test stopped runs as well as start refusals and timeouts, and ensure no other evaluation's measures are substituted. |
| Sidebar lifecycle | Test switching conversation/page while a request is in flight, signing out and signing in as another handler, focus and Escape behavior for the narrow overlay, keyboard operation of cards/confirmation, and reduced motion. Assert that a late response cannot appear in another conversation. |
| Markdown | Retain the renderer's safe handling of HTML and URLs. Test claim links, code blocks and tables so linkification does not rewrite unrelated text or produce unsafe navigation. |
| Reseed | Define what happens to Copilot checkpoint threads and active sessions when app conversations are removed. Unique conversation ids and ownership checks prevent reuse, but deleting three app tables alone does not delete `PostgresSaver` state. Do not clear unrelated claim-agent checkpoints accidentally. |
| Phase sequencing | The introduction says phases 1–5 use no real model/AWS/Supabase, but phase 5 asks for a signed-in browser check on `npm run dev`, which normally uses the real services. Move that manual check to phase 6 or explicitly use the test servers and Auth stand-in. |
| Compatibility | Use a run-start response model for the added `run_id`/`number`; do not require those fields on every existing `Accepted` response, including improvement operations. Include `npm run build` and a built-dashboard smoke check, beyond importing both Runtime entry files. |

## Suggested changes to the phases

Keep the six phases, but make these decisions part of the design before writing code:

1. **Phase 1:** settle confirmation/decision identity, turn execution ownership, terminal states, action receipts and the payment-count definition. Add the race and stale-request API tests here, plus the real-SDK logging test and transport deadline.
2. **Phase 2:** implement the loop against those contracts, including explicit tool ordering and crash reconciliation. Update structural tests for the planned extraction while preserving behavioral checks. Prove the shared context tools work with both context schemas early.
3. **Phase 3:** make the entire criteria result consistent by construction, persist the evaluation identity before waiting, and test memory against the published answer. Cover changed thresholds and negative payment counts.
4. **Phase 4:** prove execution ownership across app instances, token-safe Runtime transport, bounded startup/retries and the connection budget. Keep the deployment folders' changes narrow as planned.
5. **Phase 5:** test stale tabs, honest confirmation outcomes, conversation switching and recovery displays alongside the existing layout and end-to-end checks.
6. **Phase 6:** perform the authorized handover once after reseeding, check the deterministic report against records, confirm restart recovery, and record costs and connection use. Retain the notebook-owned deployed-memory check.

## Review evidence and limits

The review used repository source and documentation, read notebook source without executing notebook cells, and checked the installed LangGraph/ToolNode and botocore behavior relevant to the findings. The token-log probe used a fake token and fake AWS credentials with the send operation replaced; it made no network request. The plan has no Copilot implementation to exercise yet, so the proposed races and recovery paths are design findings with explicit tests to add.

No live model call, AWS deployment, live database reseed, or manual inspection of `data/evals/` was performed. Product code, the spec and the implementation plan were left unchanged.

Validation: `npm run check` passed, including the Python and TypeScript checks, isolated server/context/runtime imports, and all 24 Playwright checks. These establish the existing repository's baseline; they do not validate the unimplemented Copilot. The suite used its existing local stand-ins and temporary test databases.
