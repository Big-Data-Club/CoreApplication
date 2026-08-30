# BDC Hub Recommender and Conversational Recommender

## 1. Why this system exists

BDC Hub should help a student answer two related questions:

1. **Which course should I discover or continue?**
2. **What should I do next inside the course I am studying?**

The first question is served on normal product surfaces such as course
discovery and the student dashboard. The second can be asked naturally through
AI Mentor. Both use the same recommendation boundary so rankings, reasons,
tracking, authorization assumptions, and fallbacks remain consistent.

This document explains the implemented system, how BDC Hub currently uses it,
and how it should evolve. It deliberately separates current behaviour from
future recommendations; planned machine-learning capabilities are not described
as already deployed.

## 2. Definitions and responsibilities

| Component | Responsibility | Must not do |
|---|---|---|
| LMS | Own courses, enrolments, visibility, progress, content freshness, and candidate eligibility | Delegate access control to a ranker |
| Personalize | Build learner/profile signals and store recommendation exposure/outcome events | Become the transactional source of truth for LMS state |
| Recommender Service | Rank supplied safe candidates or produce course-bound next actions; return structured reasons and signed tracking tokens | Call an LLM or grant access to an entity |
| Conversational Recommender | Interpret a student's request, resolve context/constraints, call the Recommender Service, explain structured results, and ask for confirmation | Invent candidates, scores, reasons, or silently perform an action |
| Next.js recommendation routes | Authenticate browser requests, inject session user/role, and protect internal service secrets | Trust a browser-supplied user ID |
| Frontend surfaces | Present ranked items, preserve attribution, and emit interaction events without blocking navigation | Treat analytics delivery as a prerequisite for a user action |

The **Recommender System** is the low-latency ranking and decision service. The
**Conversational Recommender System (CRS)** is the AI Mentor interaction layer
that uses that service. The CRS is not a second ranking model.

## 3. Architecture

```text
                         explicit preferences
                    +----------------------------+
                    |                            v
Student -> Next.js UI/BFF -> LMS-authorized candidates -> Recommender Service
   |              |                    |                  |       |
   |              | inject user/role   |                  |       +-> ranked items
   |              | inject secret      |                  |           reasons/tokens
   |              |                    |                  |
   |              |                    +------------------+-> Personalize profile
   |              |                                           (short timeout/cache)
   |              |
   |              +-> impression/click/accept/reject/start events
   |                                      |
   |                                      v
   |                              Recommender validates token
   |                                      |
   |                                      v
   |                            recommender.interactions.v1
   |                                      |
   |                                      v
   |                          Personalize Bronze outcome ledger
   |
   +-> AI Mentor -> intent/scope planner -> get_recommendations tool
                                                |
                                                +-> same Recommender Service
                                                +-> RecommendationWidget
                                                +-> human confirmation
```

There are two paths:

- the **online serving path** is synchronous and should remain small, bounded,
  deterministic, and independent of an LLM;
- the **learning loop** is asynchronous: recommendation events enter Kafka,
  Personalize stores them idempotently, and analysts/models can evaluate later.

## 4. How BDC Hub uses recommendations today

| Surface | Candidate source | Current recommendation | User action and events | Failure behaviour |
|---|---|---|---|---|
| Student dashboard | Accepted LMS enrolments with progress/activity/new-content fields | Rank courses to continue or start | Top impression; click and started on navigation | Keep normal enrolment order |
| Course discovery | Published LMS courses plus enrolment state and explicit preference profile | Rank unenrolled courses | Impression, click, and accept after enrolment | Keep ordinary discovery list |
| AI Mentor chat | Current course plus Personalize course profile | Rank next actions: weak-topic review, Quick Check, continue course, or ask mentor | Impression, click, accept/reject, and started | Show retryable unavailable message |
| Lesson sidebar | Contract value exists | Not wired to a product surface yet | None | Not applicable |

Only the student role is supported. A non-student request returns a
clarification response rather than a recommendation slate.

Current policy identities:

| Decision path | `policy_version` | `model_version` |
|---|---|---|
| Dashboard and course discovery | `hybrid-rules-v2` | `hybrid-2026-08` |
| Course-bound next action/chat | `heuristic-v1` | `rules-2026-07` |

These identifiers must change when scoring semantics change, even if the API
schema stays compatible.

### 4.1 Dashboard

The dashboard supplies only courses in which the student is accepted. The
ranker excludes completed and unenrolled candidates, then prioritizes continuity
and learning momentum. Ranked items decorate the existing LMS course list; they
do not replace LMS data.

The current score is:

```text
0.28 * continuity
+ 0.22 * completion_momentum
+ 0.18 * verified_new_content
+ 0.12 * goal/topic_match
+ 0.10 * course_freshness
+ 0.10 * learning_activity_recency
```

`new_content_count` is calculated by LMS from published content since the
student's latest completion, or since enrolment when no content has been
completed. The recommender may display a “new content” badge only from that
source-grounded value.

### 4.2 Course discovery

The discovery page supplies visible published courses and marks courses in
which the user is already enrolled. The ranker excludes enrolled courses and
uses:

```text
0.30 * explicit_goal_or_category_match
+ 0.22 * level_fit
+ 0.20 * quality_adjusted_popularity
+ 0.18 * freshness
+ 0.10 * stable_exploration
```

A greedy category repetition penalty of `0.08` is applied during final
re-ranking so one category does not occupy the entire slate. Exploration is a
stable hash of learner and course, so results do not visibly jump between
identical requests.

The discovery UI lets the student store:

- interested categories;
- target career; and
- experience level.

These explicit preferences are saved by Personalize and immediately reused.
At present, the recommendation candidate pool is built from at most 100 courses
loaded for discovery metadata; it is not guaranteed to represent every course
once the catalogue exceeds that bound. Server-side candidate retrieval is a
future scaling requirement.

### 4.3 Course-bound next action

AI Mentor chat requests a recommendation for the current course. Personalize
provides `struggle_nodes`, Quick Check accuracy, and completed lesson count.
The rules create a short slate:

1. recommend weak-concept review when a struggle node exists;
2. recommend a Quick Check when accuracy is below 60% after some learning;
3. always provide course continuation; and
4. provide “ask AI Mentor” unless the student explicitly requested practice.

The available time, when provided, bounds the estimated duration. If no course
context can be resolved, the service asks the student to open or choose a
course instead of guessing one.

## 5. Cold start, degradation, and fallbacks

Cold start is not treated as a fake personalized profile.

For course discovery, the order of preference is:

1. request-time explicit preferences;
2. onboarding preferences from Personalize;
3. level fit, popularity, freshness, and stable exploration.

For a dashboard, behavioural course fields such as progress, activity recency,
and verified new content can provide useful ranking even without onboarding.

When profile retrieval fails, the Recommender Service uses safe rules and marks
`fallback: true`. The UI identifies the result as a fallback. If the entire
recommendation service fails, dashboard/discovery remain usable with their
ordinary LMS ordering. Analytics failure also never blocks navigation or
enrolment.

This degradation policy is essential: recommendation is an enhancement, not a
single point of failure for learning.

## 6. Conversational Recommender behaviour

### 6.1 Supported conversation intents

The AI planner recognizes:

- a direct recommendation request: “What should I study next?”;
- preference elicitation: “I prefer practical exercises”;
- critique/feedback: “This is too difficult; show me something else”; and
- explanation: “Why was this recommended?”

The intended turn lifecycle is:

```text
student utterance
  -> classify recommendation intent
  -> resolve authenticated user and course context
  -> extract only explicit constraints
  -> call get_recommendations
  -> receive structured RecommendationSet
  -> render RecommendationWidget
  -> show reasons/time estimate
  -> require confirmation
  -> navigate and emit outcome events
```

The tool passes a time budget only when the student stated one. It may pass an
explicit format preference (`practice`, `theory`, or `mixed`). It must not infer
a sensitive or durable preference from casual conversation.

### 6.2 Grounded explanations

Each item contains machine-readable `why_facts`, badges, confidence, expected
outcome, and estimated time. Examples include:

- `struggle_detected`;
- `low_quick_check_accuracy`;
- `course_progress`;
- `goal_topic_match`;
- `learning_activity_recency`; and
- `new_content_since_learning_activity`.

The LLM or UI may translate these facts into natural language, but it must not
claim a reason absent from the response. In particular, popularity, progress,
new content, mastery, and “students like you” claims need source data; fluent
language is not evidence.

### 6.3 Human control

The chat widget emits an impression when a recommendation is displayed. A
student first clicks “view and confirm”; navigation occurs only after explicit
confirmation. Rejection records feedback and leaves the user in place.

This confirmation rule should remain for actions that change context, start a
learning activity, enrol a user, create content, or otherwise mutate state.

## 7. Recommendation contracts

### 7.1 Internal APIs

All internal endpoints except health require `X-AI-Secret`:

- `POST /v1/recommendations`
- `POST /v1/events`

Browsers call `/api/recommendations*` on Next.js. The BFF reads the authenticated
session and injects `user_id` and role; the browser never receives the internal
secret and cannot choose another user identity.

Minimal request example:

```json
{
  "user_id": 81,
  "surface": "dashboard",
  "limit": 3,
  "context": {
    "role": "student",
    "goal": "data engineer",
    "interested_categories": ["data", "cloud"]
  },
  "conversation": {
    "intent": "request_recommendation",
    "constraints": {}
  },
  "candidates": [
    {
      "entity_id": 40,
      "title": "Data Engineering Fundamentals",
      "enrolled": true,
      "progress_percent": 45,
      "new_content_count": 1
    }
  ]
}
```

Important response fields:

| Field | Purpose |
|---|---|
| `recommendation_set_id` | Correlates one ranked slate and its events |
| `policy_version`, `model_version` | Makes evaluation and rollback possible |
| `fallback` | Identifies a degraded/cold-start policy |
| `clarification_needed` | Prevents guessing when required context is absent |
| `items[].recommendation_id` | Identifies one ranked recommendation |
| `items[].rank`, `score` | Ranking position and bounded policy score |
| `items[].why_facts`, `badges` | Grounded explanation inputs |
| `items[].tracking_token` | HMAC binding between user and recommendation |

Candidate arrays are limited to 500 by the API schema. The surface owner must
supply only candidates it is allowed to show. The target LMS route must still
re-authorize every eventual read or mutation; ranking is never authorization.

### 7.2 Feedback events

Supported event types are:

- `impression`, `click`, `accept`, `reject`, `dismiss`, `started`, and
  `completed`.

The browser sends a stable event ID of
`<recommendation_id>:<event_type>`. The Recommender Service verifies the signed
tracking token, publishes to `recommender.interactions.v1` keyed by
`user_id:course_id`, and Personalize inserts into
`bronze_recommendation_events` with `ON CONFLICT (event_id) DO NOTHING`.

Record impressions as well as positive outcomes. Without exposure data, offline
analysis cannot distinguish an ignored item from one the student never saw.

## 8. Current implementation limits

The following are real gaps, not hidden features:

| Gap | Current effect | Recommended treatment |
|---|---|---|
| Conversational critique is only logged | “Too difficult” does not yet become a ranking constraint on the next call | Convert explicit critique into turn-scoped constraints first; persist only with consent |
| Natural-language preferences are not saved by the recommendation tool | Discovery preferences persist only through the discovery profile UI | Add a confirmation-based preference-save tool |
| Chat format options are only partially applied | `practice` suppresses the “ask mentor” action; `theory` and `mixed` currently rank the same | Define and test format-aware candidate/action scoring |
| `lesson_sidebar` is declared but not connected | No recommendations are emitted from that surface | Wire it only after defining candidate source and UX |
| `completed` exists but is not emitted by current frontend journeys | True learning outcomes cannot yet be attributed to a recommendation | Carry attribution into completion events with an expiry window |
| Dashboard records only the top impression | Exposure analysis for lower visible ranked items is incomplete | Emit impressions based on actual viewport visibility |
| Discovery candidate pool is capped at 100 | Large catalogues can omit relevant candidates | Move candidate retrieval/filtering server-side or use a retrieval stage |
| Rule weights are hand-authored | Scores are explainable but not statistically optimized | Evaluate offline before shadowing a learned ranker |
| Health response reports `heuristic-v1` | Health metadata can differ from the active hybrid policy | Report deployed policy/build metadata consistently |
| Outcome events are stored but not used online | Reject/click history does not alter immediate future ranks | Build tested aggregates, then introduce them behind a versioned policy |

## 9. Recommended evolution plan

### Phase 1 - make the existing baseline trustworthy

- complete impression tracking for every actually visible item;
- emit `completed` with valid attribution when a recommended activity finishes;
- normalize role values at the BFF boundary and test student/non-student cases;
- make candidate generation server-side for large course catalogues;
- add latency, fallback rate, empty-slate rate, Kafka failure, and event-dedup
  metrics; and
- keep `hybrid-rules-v2` as the production control policy.

### Phase 2 - complete the conversational loop

- map explicit critique into structured turn constraints such as difficulty,
  excluded topic, desired format, and time budget;
- let the student edit and confirm extracted constraints before reranking;
- add a consent-based tool to persist stable preferences in Personalize;
- make “why?” answers render only returned facts; and
- retain short-lived conversation state separately from durable learner
  preferences.

Example:

```text
Student: “I have 15 minutes and that SQL lesson is too difficult.”
CRS extracts: time_budget=15, exclude_topic=SQL, desired_difficulty=easier
CRS confirms: “Use these constraints for this suggestion only?”
Recommender receives structured constraints and returns a new slate.
Student confirms one action; the system records accept + started.
```

### Phase 3 - build evaluation data products

Create reproducible datasets joining:

- slate, item, rank, surface, policy/model version;
- impression and outcome events;
- eligibility snapshot or candidate-set reference;
- course/content metadata available at decision time; and
- delayed learning outcomes such as completion or assessment improvement.

Prevent label leakage: features must reflect only information known at
recommendation time. Split evaluation chronologically and by learner where
appropriate.

### Phase 4 - introduce learned ranking safely

Only after event coverage and data quality are demonstrated:

1. train/evaluate offline against the rules baseline;
2. deploy the learned policy in shadow mode without changing UI order;
3. compare ranking, latency, coverage, fairness, and failure behaviour;
4. run a controlled experiment with stable assignment; and
5. promote only if learning outcomes improve without violating guardrails.

The LLM should remain outside the ranking path even after learning-to-rank is
introduced. Its role is intent and explanation, not unbounded candidate choice.

## 10. Evaluation framework

### 10.1 Product metrics

| Stage | Metrics |
|---|---|
| Exposure | eligible users served, slate coverage, empty-slate rate, fallback rate |
| Engagement | impression-to-click rate, accept rate, reject/dismiss rate |
| Activation | started rate after click/accept, time to start |
| Learning outcome | recommended-action completion, course progress, assessment improvement, return-to-learn rate |
| Quality | category diversity, catalogue coverage, repetition, novelty, explanation availability |
| Reliability | recommendation p50/p95/p99, timeout/error rate, Kafka publish failure, profile lookup failure |

Do not optimize click-through rate alone. A prominent but unhelpful item can
increase clicks while harming completion and learning.

### 10.2 Offline ranking metrics

Use Recall@K and NDCG@K only when positives and exposure/candidate context are
well-defined. Also report coverage, diversity, calibration by level/category,
and performance for cold-start versus established learners.

### 10.3 Guardrail slices

At minimum compare:

- new versus active learners;
- experience level;
- course category;
- low versus high activity;
- mobile versus desktop surface; and
- normal versus fallback policy.

Avoid sensitive attributes unless there is an approved purpose, access policy,
and fairness review.

## 11. Security, privacy, and governance

- LMS authorization is checked at the resource/action boundary regardless of
  ranker output.
- Browser identity is replaced with authenticated session identity in Next.js.
- Internal secrets remain server-side.
- Tracking tokens bind outcome events to a recommendation and user.
- Metadata should contain only fields required for evaluation; never copy chat
  transcripts into recommendation events by default.
- Explicit preferences need a clear edit/delete path and retention decision.
- Recommendation events are analytics data and must follow the access and
  retention rules in [`DATA_PLATFORM.md`](../DATA_PLATFORM.md).
- A recommendation may guide a learner, but must not automatically enrol,
  publish, grade, or mutate protected state.

## 12. Operations and verification

Primary implementation locations:

| Concern | Location |
|---|---|
| Online policy/API | `recommender-service/app/` |
| Policy tests | `recommender-service/tests/test_service.py` |
| Learner profiles/outcome ledger | `personalize-service/app/services/lakehouse.py` |
| Kafka ingestion | `personalize-service/app/worker/kafka_worker.py` |
| Conversational tool/planner | `ai-service/app/agents/tools/mentor/get_recommendations.py`, `ai-service/app/agents/core/planner.py` |
| Browser API boundary | `frontend/src/app/api/recommendations/` |
| Client contracts/tracking | `frontend/src/services/recommendationService.ts` |
| Chat presentation | `frontend/src/components/lms/agent/widgets/RecommendationWidget.tsx` |
| Dashboard/discovery integration | `frontend/src/hooks/useStudentDashboard.ts`, student discovery pages |

Focused verification:

```bash
cd recommender-service && python -m unittest discover -s tests
cd personalize-service && python -m compileall app main.py
cd ai-service && python -m pytest
cd frontend && pnpm exec tsc --noEmit --incremental false
```

Operational checks should confirm:

- `/health` and `/metrics` are reachable internally;
- recommendation latency remains within the product budget;
- Personalize timeouts produce marked fallback results;
- invalid tracking tokens are rejected;
- duplicate event IDs produce one Bronze row;
- Kafka failure does not block navigation; and
- dashboard/discovery still work while Recommender is unavailable.

## 13. Ownership and related documents

- Product behaviour and acceptance criteria: BA/Product
- Candidate eligibility and learning state: LMS team
- Online policy and event signing: Recommender team
- Profiles, event quality, and evaluation datasets: Data/Personalize team
- Conversation orchestration and grounded explanation: AI team
- Rendering and attribution: Frontend team
- Rollout, telemetry, and incident response: DevOps

Related sources:

- [`DATA_PLATFORM.md`](../DATA_PLATFORM.md) - Kafka and Lakehouse contracts
- [`teams/BA_HANDBOOK.md`](../teams/BA_HANDBOOK.md) - product stories and acceptance criteria
- [`teams/DEVELOPER_GUIDE.md`](../teams/DEVELOPER_GUIDE.md) - service boundaries and development workflow
- [`teams/DEVOPS_RUNBOOK.md`](../teams/DEVOPS_RUNBOOK.md) - deployment and operational guardrails
- [`recommender-service/README.md`](../../recommender-service/README.md) - concise service-level usage
