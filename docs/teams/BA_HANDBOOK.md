# BDC Hub BA Handbook

## Purpose

This handbook is the handoff boundary between Business Analysis, Product,
Design, QA, and Engineering. It describes implemented platform capabilities and
the information a development-ready requirement must contain. It is not a
promise that every planned analytic or AI capability is already available.

## Product map

| Domain | Primary user value | System of record | Delivery owner |
|---|---|---|---|
| Identity and organisations | Sign in, account/role and club administration | Auth service | Auth team |
| Learning | Courses, sections, content, quizzes, progress and forums | LMS service | LMS team |
| Coding labs | Lab catalogue, submission and evaluation | Lab service | Lab team |
| Collaboration | Course/channel chat and presence | Chat service | Chat team |
| AI learning support | Material processing, knowledge graph, quiz/flashcard and mentor support | AI service + worker | AI team |
| Personalization | Learner profile, struggle signals and analytics views | Personalize Lakehouse | Data/Personalize team |
| Recommendations | Explainable next-learning actions and outcome capture | Recommender service | Data/Recommendation team |

## End-to-end journeys

### 1. Learner studies a course

1. The learner authenticates through the frontend and receives an authorised
   session.
2. The LMS serves only content and actions the learner is permitted to access.
3. Progress, quiz, flashcard, and Quick Action interactions update LMS-owned
   state.
4. Selected micro-interactions are published asynchronously for personalization.
   Analytics failure must not silently change the learning result shown to the
   learner.
5. Personalize derives a profile; Recommender can use it to return a fast,
   explainable next-action slate.

Acceptance criteria must specify the role, course/enrolment state, happy path,
empty/error state, and the observable result. Do not write an acceptance
criterion that depends on eventual analytics data without stating its expected
delay and fallback.

### 2. Teacher creates and publishes learning material

1. An authorised teacher or admin creates course content in LMS.
2. A document/indexing operation is queued to Kafka when it needs AI processing.
3. The AI worker processes it asynchronously and emits status; the UI/job status
   must distinguish pending, completed, and failed.
4. Publication/visibility remains governed by LMS; an AI result is not proof
   that content is automatically published.

Requirements must include: who may create, edit, publish, re-run or delete;
what happens when AI is unavailable; whether the request is synchronous or a
job; and how the teacher learns the final status.

### 3. Recommendation feedback loop

1. A student asks for or sees recommendations in a course context.
2. Recommender fetches a profile and returns a rules-based slate. If profile
   lookup fails, it returns an explicit fallback slate rather than blocking.
3. The UI sends signed impression/click/accept/reject/start events through the
   recommender boundary.
4. Personalize stores these events idempotently for future analysis.

Current scope is a low-latency rules baseline. Do not describe model training,
experiment assignment, or a personalised guarantee in a requirement unless the
associated data/ML work is separately approved.

## BA-ready story template

```text
Title: <user outcome, not implementation>
Actor and role: <student | teacher | admin | system>
Context/preconditions: <course, enrolment, feature flag, prior state>
User story: As a ..., I want ..., so that ...
Rules: <permissions, validations, ordering, idempotency, retention>
Success criteria: <Given/When/Then, including exact visible result>
Failure/empty criteria: <401/403/404, dependency timeout, no data, retry>
Data impact: <LMS entity, Kafka event, Lakehouse field, personal data>
Observability: <audit event, dashboard metric, support signal>
Non-functional constraints: <latency, accessibility, privacy, mobile>
Out of scope: <explicit exclusions>
```

## Decision checklist for cross-service work

Before refinement, answer all questions below. If one is unknown, the story is
not ready for implementation.

| Question | Why it matters |
|---|---|
| Which service owns the source data and final mutation? | Prevents cross-database coupling. |
| Is the response immediate or an asynchronous job? | Defines the UI state and timeout expectation. |
| Which role can invoke it and which records are in scope? | Defines authorization and audit requirements. |
| Does it create a Kafka event or Lakehouse record? | Requires data contract, privacy and rollout review. |
| What is the fallback if AI, Kafka, or a profile is unavailable? | Prevents a non-critical dependency blocking learning. |
| How is success measured? | Connects product outcome to measurable events/metrics. |
| What may be retained, exported, or deleted? | Supports privacy and lifecycle requirements. |

## Analytics and privacy notes

- Lakehouse data is operational analytics, not a replacement for LMS or Auth
  transaction records.
- Treat user IDs, course activity, recommendation outcomes, IP address and user
  agent as potentially personal data. Define purpose, access, retention, and
  deletion handling before adding a field.
- An event consumer can receive a duplicate. Metrics and product rules must use
  an idempotency key, not raw message count alone.
- Some accepted Lakehouse input topics currently have no producer found in this
  repository. They are integration gaps, not evidence that the UX is live; see
  the Data Platform guide.

## Handoff artefacts

| Artefact | Owner | Location |
|---|---|---|
| Business requirement and acceptance criteria | BA/Product | Product tracker and linked PR |
| API and implementation detail | Service owner | Source, generated API docs, developer guide |
| Event/Lakehouse impact | Data + service owner | [Data platform guide](../DATA_PLATFORM.md) |
| Delivery/rollout/rollback | DevOps + service owner | [DevOps runbook](../DEVOPS_RUNBOOK.md) |
| Performance proof | QA/DevOps | `performance-tests/` and Grafana dashboard |
