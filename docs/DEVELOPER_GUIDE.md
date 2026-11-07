
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
