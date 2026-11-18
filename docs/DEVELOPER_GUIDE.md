## LMS request safety and quiz transactions (2026-11)

LMS owns the policy and storage boundary. `QuizPolicy` checks quiz-to-course
ownership, co-teaching and accepted enrollment; a global teacher/custom role does
not grant another course's answer key. Current published course/chapter/content
scope is required for learner reads. Callback and internal hierarchy/profile
routes require `X-API-Secret`; browser JWTs cannot invoke them. Delegated authoring
routes keep their existing service-or-user contract. JWT parsing is shared and
requires expiry. Local role lookup failures return 503; a revoked empty role set
returns 403 rather than retaining the token's old role.

Quiz code is organized by authoring, attempt workflow, grading, response mapping,
and policy. Question/options/answers use one transaction. Start/resume serializes
per learner/quiz; answer/finalize/manual grade serialize on the attempt row.
Repeated finalize returns the saved result and does not enqueue another job.
The final allowed attempt can still resume. Objective answers are batch-loaded
for finalize; no goroutine is created per answer. Learning progress/analytics are
transactional local outbox effects; AI review delivery runs separately in the same
bounded worker loop and cannot delay their commit. `ShowResultsImmediately`,
`ShowCorrectAnswers` and `ShowFeedback` apply to server responses, including
resume/history/review routes, rather than relying on frontend hiding.

Uploads keep the existing response shapes. `visibility=private|public` is an
optional multipart field **before** file parts. Documents/video default private;
passive images default public for existing thumbnail/import callers. Explicit
private images remain private. Readers resolve file owner or authorized published
course context; mutation/presign paths enforce object authorization. Linking an
existing file requires management rights to that file first. Unknown legacy
non-image objects require administrative reconciliation; old `image/` assets retain
public read compatibility. Existing private course attachments are resolved from
course ownership/enrollment. Do not infer confidentiality for an image explicitly
uploaded as public.

Browser `/files/...` requests go through the frontend file BFF, which resolves
the NextAuth session and forwards its access token to LMS. The ingress must route
this prefix to frontend without rewriting it; LMS cannot decode NextAuth cookies.
Explicit Bearer clients and anonymous public media remain supported. The proxy
preserves byte ranges/HEAD for PDF and video and returns private/no-store headers.

The body/file/batch limit is enforced while reading; at most ten files share one
`UPLOAD_MAX_SIZE` request budget (plus bounded multipart overhead). Passive inline
image/PDF content must match its extension. New file metadata owns a per-user byte
quota, serialized during registration; the default is 1 GiB via
`UPLOAD_MAX_USER_STORAGE_BYTES`. Existing unregistered objects do not count until
reconciled. HTTP file caches are private/no-store; storage buckets must also be
private. Database and object-store mutation are not a distributed transaction:
monitor failed cleanup/orphaned objects during storage outages.

Request limits are configurable: `LMS_IP_RATE_PER_MINUTE=6000`,
`LMS_USER_RATE_PER_MINUTE=300`, `LMS_COSTLY_RATE_PER_MINUTE=20`,
`LMS_MAX_REQUESTS=128`, `LMS_MAX_UPLOADS=4`, `LMS_MAX_STREAMS=128`,
`LMS_MAX_COSTLY_REQUESTS=8`, `LMS_MAX_CALLBACKS=8`, `LMS_MAX_STREAMS_PER_USER=2`,
`LMS_QUIZ_EFFECT_WORKERS=2`. Capacities are per replica; Redis rate counters are
shared. Redis failure uses a bounded local fallback, not unlimited admission.
Set `LMS_TRUSTED_PROXY_CIDRS` to the actual ingress/BFF proxy ranges; only loopback is trusted by default, rather than every private address. These are initial guardrails, not a measured capacity claim. Ordinary handlers
have a 15-second context budget; uploads/AI have two minutes; internal callbacks
30 seconds; SSE/download streams at most five minutes. Database pool sizing must
include HTTP, fixed workers, consumers and every replica. `/health` remains a
light liveness endpoint; `/ready` checks DB and Redis with a bounded deadline.
No read-path index DDL runs automatically at startup; install indexes through
forward migrations under the database owner's rollout procedure.

Validation: `go test ./...`, `go test -race ./...`, `go vet ./...` in `lms-service`.
Set `LMS_TEST_DATABASE_URL` only to disposable PostgreSQL for integration tests;
new tests create/drop unique databases, so the test role needs database-creation
permission. They cover real forward migrations, concurrent start/submit/answer,
rollback, file ACL/attachment claims, quotas, callbacks and retryable outbox work.
AI regression: `pytest tests/test_review_delivery.py`; set
`AI_TEST_DATABASE_URL` to disposable PostgreSQL for its concurrent-delivery test.
No provider calls or production data are used.


### Quiz XML and browser visibility

Teacher quiz management shows complete Markdown questions, options, accepted
answers and explanations. Editing restores the saved required flag and explanation;
content updates omit `order_index`, while new questions append after the maximum
saved position. `PUT /questions/:questionId` accepts optional `answer_options` and
`correct_answers`: omission preserves a list, `[]` clears it. Question and answer
writes commit together. Existing options carry their `id` so student answer
references remain stable; option IDs must belong to that question. Deploy the LMS
API before the frontend to enable answer editing. No migration is required.

Teachers can import Moodle XML through the quiz/question bank import preview.
XML is parsed locally without AI (2 MiB, 500 questions maximum). Embedded PNG,
JPEG, GIF and WebP images referenced through `@@PLUGINFILE@@` are previewed
locally, then uploaded sequentially through the existing authenticated LMS file
API only on confirmation. Identical bytes reuse an upload within the import.
Saved question/option Markdown contains file URLs, never base64 payloads.
Supported types: multichoice, truefalse, shortanswer and essay. Unsupported types,
non-image media, missing image attachments and incompatible weighted grading fail
explicitly before saving.
Existing authorized batch creation endpoints persist reviewed questions.

Review flags and visibility aggregates live in sessionStorage per attempt;
flags require no server writes. Visibility tracking uses `visibilitychange`, not
polling. Browser-reported departures and away seconds accompany submission in
optional `focus_summary`; the LMS validates bounds and writes the aggregate with
the attempt. This is advisory, tamperable browser telemetry, not a cheating verdict.
Closing the browser without submitting does not deliver the aggregate. Storage
failure falls back to memory. No URL history, screenshots or other tab contents
are collected. Deploy LMS migration V020 before backend/frontend rollout.
Teachers can explicitly load `GET /quizzes/:quizId/focus-report` from grading;
course ownership checks apply and results are limited to 500 recent reports.
There is no background polling, per-visibility network traffic or new Kafka event.

### Agent conversation continuity

The AI planner interprets follow-ups in the same planning call using a structured
`conversation_task`: relation (new task, continuation, revision or cancellation),
goal, artifact, output language, destination, constraints and dialogue references.
This is an interpretation, not authorization or a verified resource identifier.
The current user instruction takes precedence over recalled requests.

[`conversation_task.py`](../ai-service/app/agents/core/conversation_task.py) supplies
up to 16 dialogue messages with a 24,000-character content budget. User messages
retain up to 6,000 characters; assistant messages up to 1,800. Long excerpts retain
both beginning and end and disclose omitted text. Referenced original messages
are restored into the execution request within a separate 32,000-character source
budget, so memory packing cannot silently drop the selected problem. Unsupported
roles, missing references and references outside the supplied window are ignored.
This remains bounded context, not unlimited memory. Planner outages retain the
existing fallback and do not fabricate a resolved task.

The session's `compressed_ctx.conversation_state` stores a versioned, bounded
dialogue anchor: the planner interpretation and at most four exact user sources
(6,000 characters each, explicit head/tail excerpts for longer input). This covers
conversation/preferences as well as questions and authoring. It does not copy
assistant claims into user facts. New tasks/cancellation reset anchors; continued
exchanges retain original sources and newer corrections remain last. Only the
owner-checked session orchestrator supplies this state; sources restore within
the same UI course scope. They are context, never authorization or verified IDs.
The original PostgreSQL transcript remains unchanged.

State is saved after the user message persists, with an owner-scoped atomic JSONB
update ordered by persisted message ID. Older writes cannot replace newer state.
Failed state writes remain best-effort and do not block answering. Prompt assembly
reuses the orchestrator's owner-checked context for prompt assembly, avoiding a
second session read. Background compression accepts summary fields only,
preventing model output from overwriting server-owned
state, working anchors or consolidation cursors. No database migration is needed;
release the shared image to both AI HTTP and the consolidation worker. For the
initial rollout, update the worker before enabling new state-writing HTTP pods.

Planner data (course titles, UI hints and dialogue) now travels in the user payload,
separate from static instructions. Its gateway packer selects a compact policy,
then fits the optional course catalogue and dialogue to each actual model/key
budget, including schema-validation retries. Local message indices stay stable;
returned references are filtered against the messages actually sent on that
attempt. Current requests are never silently sliced. If required input cannot fit,
the existing gateway/fallback path reports the limit rather than inventing data.

Answer memory uses remaining input headroom after compact instructions, selected
tool schemas, current request and answer reservation. Configured tier caps still
apply. Conversation uses dialogue first; progress requests reserve learner facts.
General chat does not fetch course mastery merely because a course is open.
The final per-key packer remains authoritative: compact instructions, tool evidence
and optional schemas yield before dialogue; planned/called tool schemas and the
current request stay intact. Recent user/assistant exchanges take priority over
older dialogue, with room reserved for pinned original user sources. Before
dropping whole turns, the final packer retains token-bounded excerpts under the
original roles. These are labelled incomplete historical statements, not verified
facts or new instructions; durable semantic summaries remain a separate layer.
History omissions are disclosed. Flash keeps a
token-bounded dialogue window, no enrichment/tools and one initial answer call.

#### Layered memory and recall

The existing stores serve different purposes; none is an authorization source:

| Layer | Authority and purpose | Recall/lifecycle |
| --- | --- | --- |
| Transcript | PostgreSQL `agent_messages`: original dialogue | Owner-scoped recent window; Standard/Deep may call `recall_conversation` for older exact messages. Deleting the session cascades its transcript. |
| Hot window | Redis STM: recent dialogue cache | May expire or be trimmed after durable consolidation; PostgreSQL remains the fallback. |
| Working state | Session JSONB `conversation_state` and working anchors | Bounded original user sources and task interpretation; fresh sessions start empty instead of inheriting old topics/actions. |
| Session summary | Session JSONB `memory_items`, legacy summary fields | Select by scope, confidence and active status. Completed/superseded items remain stored, excluded from prompts. Course items require an exact known course. |
| Persistent preferences | Verified `user`-scoped preferences in owned session JSONB | Standard/Deep inspect at most 20 recent sessions for the same agent role. Only the five allowlisted preference keys with an original user message ID and exact quote cross sessions. |
| Episodes | PostgreSQL `agent_episodes`, optional Qdrant index | Standard/Deep retrieve compact historical summaries only when intent and remaining budget justify recall. No course scope means global episodes only; explicit courses add those course episodes. |

Cross-session preference selection uses source message order, so reopening an old
chat cannot overwrite a later correction. Explicit supersession keeps a tombstone;
the bounded 20-item merge retains the five preference keys while session facts
roll off. Preferences are asynchronous compressor output, not a synchronous
profile editor. Exact source matching verifies attribution, not the truth of a
user claim or perfect model interpretation. Legacy unsourced preferences stay
session-local. Deleting a source session removes its preference records; another
remaining session can still hold an older preference, so this is not account-wide
erasure. These bounded snapshots do not guarantee indefinite preference retention.

`recall_conversation` reads only the server-injected user/session, with parameterized
literal search (wildcards escaped), user messages by default, at most 20 results
and explicit 1,600-character excerpts. It reports a bounded window, not a complete
history. Assistant text remains unverified evidence. No archive read grants write
permissions or runs remembered actions. Flash has no archive tool or cross-session
preference lookup; its current-session dialogue anchors remain available.

Consolidation validates the session owner/agent before reading the transcript and
takes course scope from the persisted session, not queue hints. Episode persistence
must succeed before advancing the cursor. A compare-and-set cursor rejects stale
workers before Redis trimming. PostgreSQL stores episodes before optional vector
indexing; replay of a range preserves the canonical summary and UUID. Vector hits
are hydrated from owned PostgreSQL rows, so stale/deleted vector payloads are not
returned. Index outages use bounded recent PostgreSQL episodes, labelled as recency
with no semantic score. Missing vector entries are not automatically backfilled;
replaying an unindexed episode can retry indexing. No migration, new store or new
model call on every turn is introduced. Deploy the shared HTTP/worker image together.

#### Data integrity and execution boundaries

The planner may emit bounded `data_issues` for decisive missing inputs or unresolved
contradictions requiring the user. Explicit corrections supersede older values;
optional defaults and facts discoverable by tools should not trigger this gate.
Standard/Deep ask before answering or executing tools when an issue is reported,
even after the ordinary clarification limit. The question and issue are persisted
with role-labelled source excerpts; history indices alone are not durable evidence.
Flash retains its single-call policy guidance without the structured planner gate.
Detection depends on model interpretation; there is no universal truth validator.

Prompts distinguish user-supplied premises, source-reported claims and assistant
inferences. Memory displays user statement attribution or an unverified summary
label; a confidence score/citation never certifies truth. The parameter clarifier
receives dynamic dialogue/summary text in its user payload rather than interpolated
system instructions. Retrieved text, page context, history and memory cannot grant
identity, tool access, write scope or approval.
Deep's writer and critic share this grounding policy. A critic/provider failure
emits an unavailable-check error and no approval or fabricated perfect scores.

[`registry.py`](../ai-service/app/agents/tools/registry.py) checks verified identity,
agent catalogue membership, current disclosed schemas, reserved/unsupported arguments,
required fields and unresolved data before execution. Internal context is injected
into a copy; model-supplied `_...` or `execution_plan` fields are rejected. Disclosure
is tracked after per-model/key schema packing. Course IDs are checked against the
execution context and reauthorized through LMS at tool execution. Course-bound
reads fail closed without a target; several courses require separate authorized
calls. Teacher operations require ownership/co-teaching; shared reads and the MCP
course-knowledge reader allow accepted enrollment. Permission checks and canonical
vector hydration add bounded LMS/PostgreSQL work, not another model call per turn.
Browser course hints never mark a cache entry verified or overwrite the verified
cache on each chat request. Standard/Deep recheck their focused course before
memory, dossier or specialist reads; a revoked scope stops the turn. The retrieval
specialist cannot use a browser content ID alone for an unscoped private read.

Chat omits direct-write tools and denies forged calls to them, including publishing
lessons/quizzes, applying blueprints, saving knowledge maps, indexing and direct
notebook saves. Existing editable draft tools still return approval previews;
existing UI controls perform approved writes through their normal authenticated
APIs. MCP retains its separate credential write-scope and course checks. Its write
lane is supplied only by the adapter, never tool arguments; MCP caller confirmation
remains an external-client contract, not independent proof of a human click.

For source-based chat drafts/imports, `source_text`/`raw_text` must be an exact excerpt
of supplied user/page text or retrieved evidence collected this turn. Reconstructed
or invented source data is rejected. Exact matching verifies copying, not semantic
truth, completeness, or the absence of malicious prose in the source. Review remains
required. A course lookup failure cannot reset a draft's retrieval to unscoped mode.
RAG and vector search require a positive course ID before embedding, translation,
or retrieval. Missing/invalid scope is rejected; an explicit empty content scope
returns no evidence. Hierarchical RAG cannot expand into the global private corpus
or adopt a different course from content hierarchy hints. Pinned quiz references,
parent hydration and graph enrichment remain within the source course. Vector candidates are hydrated from
ready PostgreSQL chunk rows with course/node/content filters; stale, deleted and
out-of-scope index payloads do not become evidence. No migration or dependency is
added. Release the shared AI HTTP/worker image; no frontend contract or Kafka
payload changes are required.

Parameter clarification reads the same dialogue and planned task. Worked solutions
destined for course chapters use the editable content-draft workflow; a source exam
question alone does not imply quiz creation. A clear teacher draft request that
receives only prose gets at most one recovery turn. Attempted draft tools, including
failed calls, are not retried by that recovery guard. Repeated prose-only responses
report that creation is incomplete. Course/resource authorization, Flash's no-tool
contract and human approval of publication remain in their existing owners.

Offline regression coverage: `tests/agents/test_conversation_task.py` in AI service.
Mocked model tests verify context transport, failure handling and the approval
workflow; they do not measure real-provider semantic accuracy.
`test_dialogue_budget.py`, `test_dialogue_runtime.py` and
`test_conversation_state.py` cover small/large tiers, ordinary conversation,
corrections, source retention, worker boundaries and resumed sessions.
`test_conversation_state_postgres.py` uses an explicit disposable
`AGENT_STATE_TEST_DSN` to verify JSONB merging, ownership and concurrent ordering.

### Video and YouTube indexing

Video indexing keeps uploaded-video audio transcription (FFmpeg + local
faster-whisper). YouTube tries published captions first, then public audio via
yt-dlp with Node 22 EJS, reusing that same transcriber and timestamped chunker.
The audio fallback excludes live/unknown-duration videos, respects the existing
video duration/size limits, uses bounded network retries and a progress deadline,
and removes temporary files. It uses no cookies or authentication bypass; blocked
audio/captions require an original upload or captions. Audio is normalized to
16 kHz mono FLAC before transcription.

Node extraction measures the complete prompt against the task's preview budget,
reserving output and headroom. Oversized batches/chunks split without discarding
text or changing evidence IDs; a smaller actual model/key can trigger further
splitting. Extraction errors propagate to the worker's existing failed status;
only a successful empty extraction may produce an indexed document without nodes.
Release the shared AI HTTP/worker image to install the new yt-dlp/EJS dependency
and Node binary. No migration or event payload change is required.

### Farm learning attempt delivery

Farm answers queue LMS attempts in the same game transaction. After a successful
commit, a nonblocking local signal wakes the LMS dispatcher; rolled-back writes
do not signal delivery. The dispatcher drains at startup and uses a one-minute
fallback for missed signals, other replicas, and pending retry times. Idle LMS
outbox database checks are reduced from 30 to 1 per minute per replica. New
signals respect the existing 5–60 second failure cooldown. Durable outbox rows
and LMS challenge-ID deduplication remain authoritative, so restart recovery
needs no new infrastructure or database migration. See `farm-service/README.md`
for diagnostics. The separate Kafka reward dispatcher is unchanged.

### Teacher quiz results and AI insights

The quiz management toolbar opens `/lms/teacher/quiz/:quizId/results`.
LMS authorizes the course creator, co-teachers and admins for all four routes:

- `GET /quizzes/:quizId/results`: a whole-quiz aggregate snapshot, question statistics,
  answer choices and selection counts. Attempts include nullable browser focus data;
  IP addresses, user agents and email addresses are excluded.
- `GET /quizzes/:quizId/results/attempts/:attemptId`: answers only after verifying
  that the attempt belongs to this quiz.
- `POST /quizzes/:quizId/results/insights`: queues analysis of the authorized
  aggregate snapshot and returns HTTP 202 with `job_id`.
- `GET /quizzes/:quizId/results/insights/:jobId`: rechecks course access and the
  job's quiz scope; generic AI job polling rejects these jobs.

Charts and question counts use submitted attempts only. Score averages, pass rates
and score histograms exclude attempts with pending answer grades or missing scores;
repeat attempts count independently. A separate learner table shows their best and
average completed score. Unknown focus data stays unknown. Browser visibility is
advisory, not a cheating conclusion. CSV exports the current filtered page and escapes spreadsheet formula prefixes.

`attempt_page` and `student_page` are independently bounded pages (50 rows each,
starting at 1); `search` matches literal learner name/ID, with a 100-character limit.
`summary` and `distribution` always describe the entire quiz, independent of pages
or search. Answers are aggregated once; materialized report inputs project only
choice IDs rather than retaining essay/file answer bodies. The report uses existing
quiz/answer indexes. Redis caches authorized report pages for 15 seconds and a
per-process singleflight group coalesces identical cache misses. The overview cache
is shared across every page/search, so those requests fetch only the visible rows
and their learner aggregates instead of rescanning all quiz answers. Database work has
a 10-second timeout and does not continue indefinitely after a browser disconnect.
Authorization still runs before every cache hit. Searches debounce for 350 ms;
status polling backs off to 10 seconds. Charts and attempt details load separately.

A Redis SET NX gate reuses one quiz analysis job for five minutes across LMS
replicas, limiting repeated model calls. The AI payload carries aggregate metrics
and a five-bin histogram, not a per-attempt score array; its size does not grow with
the learner count. Queue failure stores a failed status and shortens this gate to
five seconds. The UI explains the report and analysis freshness windows.

Quiz planning now uses `quiz_gen` for both evidence budgeting and the model call,
not `content_studio`. Evidence preflight uses the largest configured request envelope
so a small fallback cannot veto a viable primary; the gateway still budgets the
actual selected model/key. An impossible context request returns a useful 422.

Deploy AI migration V024 and the AI HTTP/worker image, then LMS, then frontend.
Bootstrap registers `quiz_insights` with the standard default binding and warms its
binding cache. Admins may assign a dedicated model through LLM task bindings without
changing quiz generation. Existing admin-configured bindings remain authoritative.
No live provider call is made by the new registration/warmup itself.

Validation: `go test ./...`, AI pytest, frontend TypeScript/ESLint. PostgreSQL
regression: set `QUIZ_RESULTS_TEST_DSN` to an isolated database with CREATE SCHEMA,
then run `go test ./internal/repository -run TestQuizResultsIntegration -v`.
The fixture creates a unique schema with synthetic learners and drops it afterwards.


### Course discovery without mastery (rules v5)

Discovery is a cold-start course ranking path and never requires skill mastery.
Per-course mastery remains specific to next-lesson suggestions. A signed global
account role may differ from the LMS role: `/api/recommendations` verifies the
session access token against LMS `/api/v1/me/roles` before injecting `student`.
Browser-supplied role and user ID cannot override that decision. The existing
2.5-second serving deadline includes this membership check.

Empty candidate slates do not fall through to next-lesson/course-ID clarification.
Frontend displays empty/clarification responses explicitly instead of claiming
successful personalization of zero courses. Rules v5 match the strongest of the
learner's independent interests; adding React/Cloud does not dilute a Python
course's relevance. A bounded Research Engineer topic rule boosts research,
statistics and ML tooling; missing course level is neutral. These remain lexical
rules, not semantic model inference. Deploy recommender and frontend together;
no mastery backfill or migration is needed.
