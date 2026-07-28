# ADR-4: Verified Agent Context and Human Approval

## Status

Accepted

## Decision

Every agent turn receives a structured browser context, but treats it only as
a hint. Before an LLM plan is generated, `context_foundation.py` normalizes it
and verifies its course ID against the user's server-loaded active courses.

The resulting snapshot is small and explicit:

- user role (from the authenticated server session)
- route and page type
- course, section, content, and quiz identifiers/title where applicable
- whether lesson body is available (the body is not included in telemetry)
- resolution status, confidence, and source of the decision

Course resolution is deterministic and follows this order:

1. verified explicit course scope;
2. verified course from the active page;
3. a unique course title named in the message;
4. the only active course;
5. ask the user to choose, if a course-bound action has several candidates;
6. offer confirmed navigation to the course list, if a course-bound action has
   no candidate;
7. remain global for questions that can safely be answered without a course.

No unverified browser course ID or planner-proposed course ID is used unless it
exists in the active-course list.

## Human-in-the-loop contract

Any action that changes the workspace must be represented as a pending approval
or as an editable specialised draft widget. Navigation is also offered as a
confirmable action. The generic approval card currently implements safe local
navigation only; content and quiz widgets remain the owners of their editable
draft and save flows. New action tools must return `pending_human_approval`
and one of:

- an editable dedicated widget which performs the final write after approval;
- a generic approval payload with a non-mutating confirmed action.

Tools must never write LMS content merely because an LLM selected a function.

## Performance and privacy

The resolver is a pure, in-process operation and runs after the already-needed
active-course cache lookup but before planner/retrieval model calls. It avoids a
planning call entirely for missing-course routing and course selection. Page
body is sent only through the existing lesson grounding path; it is not
persisted in the turn-context event or chat metadata.

## Extending this foundation

New scenarios should add a deterministic, tested context policy first (for
example: quiz attempt, assignment deadline, organisation scope), then add an
agent planner/tool. The frontend must declare the relevant IDs through
`PageContext`; the backend must verify any ID against an authoritative service
or the user's permitted resource list before acting on it.
