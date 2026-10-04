# LLM gateway operations

All text and vision calls from `ai-service` route through the LLM gateway. The
gateway stores provider keys encrypted, applies task-to-model bindings, tracks
usage, and manages fallback/cooldown centrally.

## Optional Jev decision service

Jev System One is a structured decision API. On first startup the gateway
registers the `opencode_zen` provider, the `jev-1.13-free` model, and a
`jev_decision` task binding. This is a catalog default only: runtime resolves
the active task binding, model, provider URL and encrypted key pool from the
gateway. Admin changes are retained across restarts. The application default
is disabled; the production ConfigMap opts in. Without a usable binding/key,
routing uses the existing local rule. To disable after rollout, set
`JEV_ENABLED=false` and restart `ai-service`.

To choose another provider or System One model, create it in Admin > LLM
Configuration. Set the model's JSON config to `{"api_protocol":"system_one"}`;
optionally set `endpoint_path` (default `systemone`). Give its provider an HTTPS
Base URL and an active API key, then add the model to the `jev_decision` task
binding chain with a higher priority or pin it. Only System One models can be
bound to that task. Key and binding changes take effect without a pod restart
(binding caches on other processes can take up to 30 seconds). The gateway
appends the model's endpoint path to its provider's Base URL.

For read-only Deep questions, Jev evaluates up to 900 characters of the current
question and returns an advisory probability for the retrieval/draft/critique
pipeline. A score of at least 0.85 may promote a local score in the 0.35–0.45
band. It cannot approve writes or bypass course authorization. MCP also exposes
the read-only `assess_question` tool for explicit assessment, returning an
unavailable error when Jev is disabled. Operators should review the external
transfer and provider retention terms before enabling the feature in production.
System One models must not be bound to chat tasks.

### Bounded standard-chat planner accelerator

Deployment configuration explicitly sets `JEV_PLANNER_MODE=active`; the code
default remains `off` when configuration is absent. The general Jev switch and
planner mode are independent. Its policy is `course_qa_v1`.

- `off`: use the original planner without an extra external request.
- `shadow`: evaluate eligible requests alongside the original planner, always
  return the original plan, log differing plan fields, and cancel the evaluation
  if the planner finishes first. Incomplete evaluations are not disagreements.
- `active`: skip the LLM planner only when every named decision meets
  `JEV_PLANNER_MIN_SCORE` (default 0.97, allowed range 0.95–1). Otherwise run the
  original planner with the complete original inputs.

Both non-off modes also require `JEV_ENABLED=true` and a usable managed binding.
`JEV_PLANNER_DEADLINE_SECONDS` defaults to 0.8 (allowed range >0 to 2.5); it
bounds the complete evaluation, including binding/key lookups and retries,
rather than each HTTP attempt separately. An active fallback can add this
budget to the original planner latency. Cancellation is propagated.

Eligibility is deliberately narrow: standard mode, mentor, no conversation
history or page/system context, one active course matching the resolved course,
a nonempty course title up to 300 characters and a question of 5–900 characters.
Common action terms bypass Jev locally. The evaluator must affirm all three
conditions: a course-material question, standalone context, and read-only intent.
Only the question and course title are sent, without explicit learner IDs or
history; user-authored question text can itself contain personal information.
No truncation is used on this path. Scores are validated without rounding.

The accepted template selects `search_course_materials` and `explain_concept`,
keeps GraphRAG/weakness signals, and caps planned retrieval expansion to the
course. It does not execute tools or set a new course ID. Existing context,
clarification, tool authorization, recovery and approval checks still run.
Tool disclosure is guidance, not a permission boundary. Flash, Deep, teachers,
follow-ups, lesson context and multi-course requests use their previous paths.

Roll out with `shadow` first on a controlled environment. `Jev planner` logs
record policy, mode, eligibility, accepted decision, decision availability,
decision duration, total evaluation/planner duration and differing plan fields;
they do not log question text. Gateway usage remains under `jev_decision`.
Review differences with labelled Vietnamese/English requests, including mixed
read/write requests, negation, ambiguous references, scope pivots and requests
for learner data. A high provider score is not measured routing accuracy.
Compare routing correctness, grounded answer quality, time to first tool,
end-to-end p50/p95 latency, fallback rate and total provider cost against `off`.
Use a controlled active canary only after those results support it; shadow
planner agreement alone does not establish answer quality or a speedup.
Rollback by setting `JEV_PLANNER_MODE=off` and restarting the AI HTTP workload.
No database migration, worker change or event-contract rollout is required.

See [ADR-6](adr/ADR-6-bounded-jev-planner.md) for scope and expansion criteria.

## Default routing

Text tasks bootstrap to the configured default model. `agent_flash`, used only
by the chat UI's Flash mode, reads `AGENT_FLASH_MODEL` at startup; when it is
empty, it uses `CHAT_MODEL`. This keeps the latency-first path independent from
the tool-capable `agent_react` binding without pinning a provider model in
source. A vision task keeps its separate vision-capable binding; do not bind a
text-only model to it.

For Compose and K3s, set `AI_FLASH_MODEL` in `.env`; the runtime manifests map
it to `AGENT_FLASH_MODEL`. The K3s runtime preparation script now copies that
setting (and `LLM_REQUEST_TOKEN_BUDGET` / `LLM_TPM_SAFETY_RATIO`) into its
override ConfigMap, so the selected gateway model is not lost at deployment.
For a Groq key with an 8K TPM allowance, the shipped request budget is 6K with
a 0.75 safety ratio. Raise those settings only after updating the key's TPM
limit in the gateway configuration.

Change a model, fallback order, TPM/RPM limit, or API key in
`/lms/admin/llm-config`. Admin-created or pinned bindings are not overwritten
by application startup. Set `AI_FLASH_MODEL` in runtime configuration before a
first bootstrap, or bind a faster approved model to `agent_flash` in the admin
UI. Do not repurpose `agent_react`, which serves the standard and deep tool
workflows.

## OpenAI API key

ChatGPT subscriptions and API billing are separate. Enable API billing at the
OpenAI Platform, create an API key, then add it in **Cấu hình LLM → Keys** to
the built-in **OpenAI API** provider. The key is encrypted before it is stored.

`OPENAI_API_KEY` is an optional bootstrap mechanism for deployment. Put a real
key only in the runtime secret manager, never in this repository. The shipped
Kubernetes value is a deliberately ignored placeholder.

## Large-course overview generation

The overview workflow is coverage-preserving map/reduce:

1. Every source chunk is put into a bounded local synopsis batch.
2. Large sets of synopses are progressively reduced to evidence cards.
3. The final Vietnamese/English lesson uses the evidence cards, with source
   references retained.

No source text is silently truncated. The gateway also preflights estimated
input + output tokens, including tool schemas and tool-call metadata, and
respects the configured request budget and a key's TPM limit before calling a
provider.

### Retrieved materials but no final agent answer

A successful `search_course_materials` event only confirms retrieval. The
answer-only synthesis can still fail independently. ReAct now converts tool
results to quoted user data before the synthesis request, without sending
historical `tool_calls` or `tool` roles to a provider with no `request.tools`.
Evidence selection still runs against the selected model/key input allowance.
During normal tool rounds, prompt packing retains schemas referenced by prior
calls; if those cannot fit, the gateway must try another capacity envelope.

For a failing turn, correlate its session with `Final synthesis failed after tool
rounds` and inspect the error type. Persisted completion reasons distinguish
`synthesis_failed`, `synthesis_empty`, and `max_iterations`. A synthesis ending
with a length limit is marked incomplete rather than reported as complete.
Deploy the updated AI image before retesting; previously saved incomplete
messages are not regenerated by deployment. Retrieval success alone does not
establish provider availability, a valid final-answer request, or deployment of
the fix.

### Deep answers cut off in a sentence or table

Deep now uses a shared answer-completion policy for the ReAct answer, final
answer-only synthesis after tool rounds, and multi-agent drafting/revision.
Previously the latter two paths could stop after just 2200/2048 output tokens.
Increasing tool iterations alone does not fix answer truncation.

Defaults (AI HTTP workload, restart after changing):

| Setting | Default | Meaning |
| --- | --- | --- |
| `AGENT_DEEP_MAX_ANSWER_CONTINUATIONS` | 12 | Maximum extra answer calls; 0 disables continuation |
| `AGENT_DEEP_MAX_ANSWER_TOKENS` | 24000 | Estimated visible answer size, including its first segment |
| `AGENT_DEEP_ANSWER_CHUNK_TOKENS` | 4096 | Requested output per call, clamped to remaining budget |

These are ceilings, not targets. Normal completion stops immediately. On
`length`/`max_tokens`, the system resumes from the answer tail, retains the
original question, removes overlap and asks to finish open Markdown tables,
code blocks and sentences. The last budgeted call asks for a concise finish.
No-progress/repeated output stops the loop. Content-filter/safety termination
is never retried. Missing terminal events and retryable transport failures
allow at most two recovery calls within the same continuation budget. An
interrupted continuation preserves the new text before resuming. Client
cancellation propagates rather than launching more work.

Continuation is answer-only: it does not re-execute tool calls. Fresh prompt
packing retains the continuation instruction instead of reusing a packer
closure bound to the original request. Gateway context, TPM, key availability
and model output caps remain authoritative. Visible-token estimates are not
provider billing totals; reasoning tokens and a separate critique-driven
revision can add cost. Standard now allows eight extra calls and 16000 estimated visible-answer tokens,
with a 4096-token per-call cap, including initial ReAct and tool synthesis.
Configure these using `AGENT_STANDARD_MAX_ANSWER_CONTINUATIONS`,
`AGENT_STANDARD_MAX_ANSWER_TOKENS`, and `AGENT_STANDARD_ANSWER_CHUNK_TOKENS`.
Flash retains its three-call/6000-token defaults. The Deep tool-execution round limit is unchanged.

Synthesis emits completed segments as they become available. The HTTP SSE
endpoint sends a comment keepalive every 15 seconds while waiting for model or
tool output and cancels pending generation on disconnect. This helps with idle
timeouts; it cannot override an external proxy's absolute request timeout or
restore a disconnected browser session.

Inspect saved `incomplete`, `finish_reason`, `answer_continuations` and
`answer_stop_cause` metadata. Exhausted budgets remain visibly incomplete;
multi-agent drafts no longer silently report truncated output as complete.
Test a long Deep answer containing a table, a forced provider length limit,
transport interruption, and cancellation after deployment. Existing stored
partial answers are not regenerated automatically. To reduce cost/latency,
lower the Deep ceilings; do not remove the incomplete indication.

### Repeated routing scores and missing learner context

S-Score factors are discrete policy signals, not learned per-user scores.
For example, intent 0.1 + retrieval 0 + verification 1 + page 1 + depth 0.8
contribute `0.3*0.1 + 0.1*0 + 0.15*1 + 0.2*1 + 0.1*0.8 = 0.46`, before
context pressure. The planner/router now validate canonical intent categories
and normalize operation aliases such as `content_qa` to `knowledge_question`.
Unknown categories fail validation into the existing planner fallback.

Deep drafting and revision now receive the bounded memory section, plain
recent dialogue, and learner snapshot when prepared. Critique receives the
learner context separately from cited course evidence. The decision explanation
adds optional `memory_forwarded`, `personalization_context_prepared`,
`profile_fetch_status`, `conversation_messages_available` and
`conversation_history_excerpted` fields. Existing status fields remain
compatible. These indicate prepared inputs; gateway packing may still reduce
them. They are not proof of correct model understanding.

Course-profile fetch remains authenticated through the existing internal
Personalize API, scoped to the authenticated chat user and resolved course.
It is independent of whether the separate mastery snapshot is enabled. Profile
counts/accuracy and returned identity are checked before prompt injection.
`profile_fetch_status=error` covers transport/HTTP/error-payload/invalid-response
failures; `empty` means a valid successful response with no measured activity.
No Kafka topic, profile API, persistent schema or retention policy changes.
The source remains `lms.analytics.interactions` → Personalize ingestion → course
profile. A zero score or empty explanation alone cannot diagnose live ingestion.

Deploy backend and the updated frontend together for the corrected explanation;
the added fields are optional for compatibility. Previously stored explanation
metadata is not recomputed. Verify with a new chat turn for an enrolled learner
with known course activity and a follow-up after a long Deep response. Correlate
profile fetch failures with Personalize availability/authentication and its
worker ingestion rather than enabling global personalization indiscriminately.


### Conversation continuity and message feedback

- Agent chat reads a bounded recent window (30 messages) from owner-scoped PostgreSQL history as well as Redis. Expired or stale Redis no longer makes an existing conversation appear new; prompt budgeting still excerpts long dialogue. Redis append failures are non-fatal. If both reads fail, the memory prompt states that history is unavailable.
- Existing session IDs must belong to the authenticated user and agent type; a missing session no longer silently creates an empty replacement. A model error after visible text saves that partial answer with `incomplete=true` and returns its message ID for feedback. Abrupt process termination or client cancellation is not a durable streaming checkpoint.
- Internal `GET /ai/agents/sessions/{session_id}/messages` now requires `user_id` injected by the authenticated frontend proxy. It returns the newest bounded messages chronologically and the caller's `feedback` (`like`, `dislike`, or null). Deploy the frontend and AI service contract together.
- `POST /ai/agents/feedback?user_id=...` requires an owned assistant message. An explicit null `rating` removes an existing rating; omission is invalid. The existing V012 feedback table is reused. The UI confirms selection only after persistence succeeds and displays a retry message on failure. Historical clicks never persisted cannot be reconstructed.
- Validate a conversation across Redis expiry, a failed answer, reopening the session, and like → dislike → deselect → reload. Automated checks mock storage; staging validation with actual PostgreSQL/Redis and a model is still needed.

### Lead-planned multi-agent collaboration

`AGENT_LEAD_MODE=active` enables a lead planning/preparation stage on eligible
Deep multi-agent requests; deployment configuration now selects `active`.
The code default remains `off` only when no environment value is supplied.
This is independent of the Standard-mode `JEV_PLANNER_MODE`. The lead uses
`agent_router`; delegated analysis uses `chat`; System One assessments use
`jev_decision` only when `JEV_ENABLED=true`. Existing final writer and critic
bindings remain unchanged.

There are at most four preparation workers, two concurrent, with selected
shared-context reads and bounded artifacts. Invalid plans, unavailable
executors and timeouts fall back to the established pipeline before answer
streaming. Existing trace events include `lead_plan`, per-worker executor and
context keys, and `lead_fallback`; message metadata retains orchestration
selection. Enable on staging and assess actual quality/latency/cost first.
See [ADR 7](adr/ADR-7-bounded-lead-agent-collaboration.md) for exact limits and
memory/permission boundaries.
