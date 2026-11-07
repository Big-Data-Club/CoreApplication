
### Quiz XML and browser visibility

Teachers can import Moodle XML through the quiz/question bank import preview.
XML is parsed locally without AI or file uploads (2 MiB, 500 questions maximum).
Supported types: multichoice, truefalse, shortanswer and essay. Unsupported types,
attachments and incompatible weighted grading fail explicitly before saving.
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
