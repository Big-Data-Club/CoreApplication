
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
