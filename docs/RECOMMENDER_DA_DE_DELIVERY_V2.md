# BDC Recommender v2 — Delivery Brief for DA and DE

| Field | Value |
|---|---|
| Status | Proposed implementation plan |
| Version | 2.0.0 |
| Date | 2026-07-28 |
| Owners | Data Analytics (DA), Data Engineering (DE); product sign-off by LMS/AI owners |
| Scope | Student next-best-action, learning roadmap, course discovery, and conversational recommendation |

## 1. Executive decision

BDC already has a useful **analytics/personalization foundation**, but it is not
yet a production recommender. The current `personalize-service` receives
`lms.analytics.interactions`, persists Bronze/Silver/Gold data in DuckDB, and
exposes heuristic study and discovery recommendations. The AI agent already
loads a personalization profile when it creates a study plan. Keep this as the
baseline and safe fallback; do **not** put a high-QPS online ranker directly on
DuckDB Gold views or make the LLM decide which database IDs to recommend.

Build a separate online **recommender service**. It owns candidate retrieval,
eligibility, ranking, exploration policy, recommendation identity, and outcome
logging. `personalize-service` remains the nearline/offline profile and
Lakehouse producer. LMS, frontend, and AI agent become consumers.

The v1 product principle is:

> Recommend a small, useful next learning action that is allowed by the
> curriculum and explainable from real evidence. Optimize for learning progress,
> not for clicks alone.

## 2. What exists today and what changes

| Existing implementation | Keep / change | v2 consequence |
|---|---|---|
| `lms.analytics.interactions` / `MicroInteractionEvent` | Keep as compatibility source; extend | It lacks session, surface, impression position, recommendation ID and outcome fields needed to train/evaluate ranking. |
| `personalize-service` DuckDB Bronze/Silver/Gold views | Keep | It is the analytics source, backfill source, profile/struggle producer and heuristic fallback. |
| `gold_study_recommendations` | Keep as `heuristic_v0` | Use it as an explicit baseline in offline and online experiments; do not present it as an ML ranker. |
| `gold_course_discovery_recommendations` and handmade vectors | Keep only as initial candidates | Replace cross-join/vector score serving with a candidate-generation + ranker pipeline as traffic grows. |
| AI `get_study_plan` and context builder | Integrate | The agent receives a bounded recommendation context; LLM explains, asks a clarifying question, and obtains confirmation for actions. |
| Qdrant and knowledge/mastery data | Reuse | Semantic retrieval and prerequisite/mastery eligibility are candidate sources and hard constraints. |

Recommended repository boundary:

```text
LMS / Frontend / AI agent
        │  request + events
        ▼
recommender-service                 <---- online feature cache / catalog snapshot
  candidate generators              <---- mastery + profile updates
  eligibility & diversity
  ranker + exploration policy
  recommendation ledger
        │
        ├── response to LMS/frontend/chatbot
        └── Kafka recommendation.* events
                 │
                 ▼
personalize-service lakehouse → validated Silver/Gold/model datasets → DA training
```

The ranker must be fast and deterministic. LLM calls belong **after** ranking,
only for natural-language explanation, preference elicitation, or a draft
roadmap. They must never bypass eligibility rules or invent item IDs.

## 3. Product surfaces and objectives

### 3.1 Four recommendation products

| Product | Candidate item | Primary outcome (label) | Typical surface |
|---|---|---|---|
| Next-best action (NBA) | review, lesson, quiz, flashcard, ask mentor | starts within 24h **and** meaningful completion/mastery signal within 7d | course/lesson page, dashboard, chatbot |
| Learning roadmap | constrained ordered sequence of actions | roadmap step completion + diagnostic/mastery improvement | dashboard, chatbot |
| Course discovery | eligible course | enroll plus active learning within 7d | course catalogue/home |
| Conversational recommendation | the same items, conditioned by current dialogue constraints | accepted/refined action and downstream learning outcome | agent/chat sidebar |

Do not merge these into one model at first. Each has a different candidate
universe, eligibility logic, and success label.

### 3.2 Non-negotiable constraints

1. Recommend only published resources the user may access.
2. Never recommend an unfinished prerequisite as if it were an advanced next
   lesson. A prerequisite repair action is allowed.
3. Respect teacher settings, deadline/availability, language, role, and user
   personalization opt-out.
4. Suppress completed, dismissed, already-open items, unsafe links, and repeated
   recommendations within configured cooldowns.
5. Every displayed item has a stable `recommendation_id`, `policy_version`,
   `model_version`, `rank`, and `propensity` logged before exposure.
6. New policy/model must have a rules-based fallback, kill switch, and canary.

## 4. Canonical contracts (the DA/DE shared boundary)

All timestamps are UTC ISO-8601. IDs are opaque strings or int64s; no names or
raw chat messages are sent as analytics fields. The schema is versioned (`v1`)
and validated at the producer and consumer.

### 4.1 `lms.learning.interaction.v1`

**Purpose:** immutable user behaviour and learning outcome event. Kafka key:
`user_id:course_id`, enabling ordered per-course processing.

```json
{
  "schema_version": "1.0",
  "event_id": "0fbd4d2d-8c1d-46cb-9e95-3aacd42e6725",
  "event_time": "2026-07-28T10:14:32.419Z",
  "user_id": 481,
  "role": "student",
  "session_id": "s_01J...",
  "surface": "lesson_sidebar",
  "course_id": 38,
  "section_id": 204,
  "lesson_id": 1909,
  "knowledge_node_id": 914,
  "entity_type": "quiz",
  "entity_id": "quiz:922",
  "event_type": "quiz_submitted",
  "value": {"score": 0.5, "max_score": 1.0, "duration_ms": 64000},
  "recommendation": {
    "recommendation_id": "rec_01J...",
    "request_id": "rr_01J...",
    "rank": 2,
    "policy_version": "nba-v1",
    "model_version": "lgbm-2026-07-28",
    "propensity": 0.10
  }
}
```

Required event types for the first release:

```text
impression, click, dismiss, save, accept, reject,
lesson_started, lesson_completed, quiz_started, quiz_submitted,
flashcard_reviewed, mentor_opened, roadmap_created, roadmap_step_started,
roadmap_step_completed, course_viewed, course_enrolled
```

`impression` is mandatory whenever a recommendation becomes visible. `click`
is not a substitute for success. `accept`/`reject` is explicit feedback from
chat or a card. Client retries must retain `event_id`; DE deduplicates by it.

### 4.2 `RecommendationRequest`

```json
{
  "request_id": "rr_01J...",
  "user_id": 481,
  "surface": "chat",
  "candidate_types": ["next_action", "roadmap_step"],
  "limit": 3,
  "context": {
    "role": "student",
    "course_id": 38,
    "lesson_id": 1909,
    "locale": "vi-VN",
    "time_budget_minutes": 20,
    "goal": "prepare_for_quiz",
    "session_id": "s_01J..."
  },
  "conversation": {
    "turn_id": "turn_85",
    "intent": "request_recommendation",
    "constraints": {"prefer_format": "practice", "avoid_topics": []}
  }
}
```

`course_id` and `lesson_id` originate from the verified agent context
foundation, not from LLM output. Missing scope is valid: the service returns a
global/cold-start result or a `clarification_needed` flag; the chatbot asks the
single highest-value question.

### 4.3 `RecommendationResponse`

```json
{
  "request_id": "rr_01J...",
  "recommendation_set_id": "rs_01J...",
  "policy_version": "nba-v1",
  "fallback": false,
  "clarification_needed": false,
  "items": [{
    "recommendation_id": "rec_01J...",
    "entity": {"type": "lesson", "id": "1909", "course_id": 38},
    "action": "review_then_practice",
    "rank": 1,
    "score": 0.83,
    "tracking_token": "signed-short-lived-token",
    "why_facts": [
      {"code": "low_mastery", "node_id": 914, "value": 0.42},
      {"code": "matches_time_budget", "minutes": 18}
    ],
    "expected_outcome": "complete a short review and one quick check",
    "estimated_minutes": 18,
    "confidence": "medium"
  }]
}
```

`why_facts` are structured, auditable facts. The UI/LLM may phrase them in
Vietnamese, but must not claim unsupported reasons.

### 4.4 Roadmap response

A roadmap is a versioned plan, not merely a list of ranked lessons.

```json
{
  "roadmap_id": "rm_01J...",
  "goal": "Pass the Linux shell assessment",
  "course_id": 38,
  "estimated_total_minutes": 110,
  "steps": [
    {"order": 1, "action": "review", "entity_id": "lesson:1909",
     "unlock_when": "mastery(prerequisite:914) >= 0.60", "minutes": 20},
    {"order": 2, "action": "practice", "entity_id": "quiz:922",
     "unlock_when": "step_1_completed", "minutes": 15}
  ],
  "reason_codes": ["weak_prerequisite", "assessment_goal"],
  "policy_version": "roadmap-v1"
}
```

## 5. Ranking architecture and optimization policy

Use the same four-stage separation used in large-scale recommenders: candidate
generation, filtering, ranking, then policy/slate construction. YouTube
explicitly documents the candidate-generation/ranking split; BDC needs this
separation even at smaller scale so model changes are safe and latency remains
predictable.

### 5.1 Candidate generation (recall)

Generate 50–300 candidates by merging and deduplicating these sources:

| Source | Best for | Initial implementation |
|---|---|---|
| Curriculum sequence + prerequisites | next learning action/roadmap | LMS course tree + knowledge graph + mastery threshold |
| Weak-concept repair | study support | `gold_concept_struggles`/`user_concept_mastery` |
| Semantic content retrieval | related material/cold item | Qdrant content embedding + topic/tags |
| Collaborative behaviour | discovery and mature courses | implicit feedback item-item/user-item model |
| Popularity/freshness/editorial | cold start and safety fallback | course/role/level-local popularity, teacher-pinned content |
| Conversation constraints | chat | hard filters for time budget, format, goal, explicit dislikes |

### 5.2 Eligibility and slate policy

Filter before model score. Then apply diversity (avoid three variants of the
same lesson), novelty, fatigue and frequency caps. A simple first scoring
function is transparent and adequate while data matures:

```text
score = 0.35 * learning_need + 0.25 * completion_likelihood
      + 0.15 * goal_match + 0.10 * prerequisite_readiness
      + 0.10 * freshness + 0.05 * diversity_bonus
```

DA tunes the weights only against agreed learning metrics. DE makes weights and
rules remotely configurable, versioned, and reversible.

### 5.3 Exploration versus exploitation

Start with **90% exploitation / at most 10% safe exploration** after the
baseline is stable. Exploration only chooses among already eligible,
high-quality candidates; it never breaks prerequisites, permission, deadline,
or teacher constraints. Use deterministic user bucketing and log the selected
policy probability (`propensity`).

Phased policy:

1. Weeks 0–4: deterministic rules + small randomized position bucket to collect
   unbiased impressions; no bandit.
2. After sufficient logged outcomes: contextual epsilon-greedy or LinUCB over
   safe candidate pool; per-course fallback and cooldown.
3. Only after offline replay and guardrails pass: contextual bandit with
   propensity-weighted evaluation. Keep a 5–10% holdout.

This is essential: clicks are position-biased. Without impression, rank, and
propensity logs, DA cannot validly compare policies or train a bandit.

### 5.4 Latency/SLO target

| Component | Target |
|---|---|
| Online recommendation API p95 | <= 150 ms; p99 <= 300 ms |
| Candidate retrieval p95 | <= 60 ms |
| Ranking + policy p95 | <= 40 ms |
| Profile/catalog cache freshness | profile <= 5 min; catalogue publish/status <= 1 min |
| Event ingestion acknowledgement | async; no user-facing wait |
| Outage behaviour | return cached/rules fallback within 100 ms and emit a metric |

Use cache-aside online feature snapshots (e.g. Redis), bounded candidate sets,
timeouts, circuit breakers and precomputed daily/nearline candidates. Do not
make synchronous cross-service calls for each feature at rank time.

## 6. Conversational recommendation and human-in-the-loop

The chatbot is an interaction layer over the recommender; it is not the
ranking engine.

```text
User message → intent/constraints extraction → RecommendationRequest
             → retrieve/rank eligible actions → agent explains choices
             → user accepts / edits / rejects → outcome event + context update
```

Supported dialogue acts: `request_recommendation`, `state_preference`,
`state_constraint`, `critique`, `ask_why`, `accept`, `reject`, and
`clarify_scope`. This extends the intent types already present in the AI agent.

Sample:

```text
Student (course 38, lesson 1909): "Tôi chỉ có 20 phút và hay sai bash condition."
Agent: [calls recommender with verified course/lesson + time=20 + practice]
Agent: "Mình đề xuất: ôn 8 phút bài Bash condition, rồi làm Quick Check 10 phút.
        Lý do: mastery ở condition đang thấp và hai bước này vừa trong 20 phút.
        Bạn muốn mở lộ trình này không? Bạn có thể sửa thời lượng hoặc chọn đọc lý thuyết."
Student: "Được, nhưng chỉ bài tập."
Agent: [updates constraint, receives practice-first result, shows confirmable card]
Student: [Confirm]
Frontend: navigates/starts only after confirmation; emits accept + started events.
```

The existing agent-context ADR remains authoritative: course/page context is
server-verified; navigation and writes remain pending approval. Simple read-only
recommendations may be displayed immediately. Opening a lesson, creating a
roadmap, enrolling, or changing study settings is a confirmable action. The
user can edit title, duration, order, or remove a roadmap step in the chat card
before confirmation; the edited fields become explicit constraints in the next
request.

## 7. Data model and quality gates for DE

### Required Bronze/Silver/Gold additions

| Layer | Dataset | Minimum content |
|---|---|---|
| Bronze | `bronze_learning_events` | full immutable `lms.learning.interaction.v1`, Kafka metadata, ingestion time, dedupe status |
| Bronze | `bronze_recommendation_exposures` | request, slate, rank, policy/model version, propensity, tracking token hash |
| Silver | `silver_learning_interactions` | normalized action taxonomy, valid entity joins, sessionized time/dwell, late-event handling |
| Silver | `silver_recommendation_outcomes` | exposure joined to click/accept/start/complete/mastery outcomes with 24h/7d windows |
| Gold | `gold_user_learning_features` | point-in-time mastery, recency, pace, preference, time budget bucket |
| Gold | `gold_item_features` | publication/access state, prerequisites, topic, difficulty, estimated time, freshness, quality |
| Gold | `gold_training_examples` | point-in-time feature snapshot, candidate, label, exposure/propensity/policy version |

Quality gates are release blockers: schema validity >= 99.9%, `event_id`
dedupe rate observable, <1% orphan entity references, null-rate dashboard,
event-time/ingestion-time lag dashboard, reconciliation with LMS quiz and
completion facts, and a documented backfill replay.

## 8. DA work packages

DA owns definitions, analysis, modeling, offline evaluation, experiment design
and model acceptance. DA does **not** directly alter production events or serve
unversioned notebooks to users.

| ID | Task | Inputs | Required output / definition of done |
|---|---|---|---|
| DA-01 | Product metric and label spec | this document; product decisions; event catalogue | Signed metric tree for each surface: primary learning label, secondary engagement label, guardrails, attribution windows, exclusion rules. No click-only objective. |
| DA-02 | Data audit and feasibility report | Bronze/Silver samples; LMS catalogue/mastery | Data dictionary, coverage by course, sparsity/cold-start analysis, leakage risks, quality issues, and minimum data threshold to move beyond baseline. |
| DA-03 | Reproducible v0 baselines | `gold_*`, catalogue, prerequisite graph | Time-based split notebook/job for popularity, curriculum rule, weak-concept, content similarity and item-item CF. Report Recall/NDCG/MRR plus completion/mastery proxy; versioned dataset snapshot. |
| DA-04 | First ranker | `gold_training_examples` from DE | Explainable LightGBM/LambdaMART (or logistic model if data is small), feature list, feature-importance/slice checks, model artifact and reproducible training config. It must beat v0 on agreed offline metric without guardrail regression. |
| DA-05 | Roadmap policy | mastery, knowledge graph, course structure, deadline/time budget | Deterministic constrained planner: prerequisite DAG traversal, remediation, estimated time and unlock criteria. Unit cases for low mastery, no course, deadline, and conflicting constraints. |
| DA-06 | Exploration and counterfactual protocol | exposure/propensity/outcome dataset | Offline replay/IPS or doubly-robust evaluation, safe candidate definition, epsilon/bandit parameters, traffic ramp and stop criteria. Do not approve a bandit without propensity logs. |
| DA-07 | CRS evaluation | de-identified intent/constraint/feedback annotations | Intent/slot taxonomy, annotation guideline, evaluation set, clarification success rate, explanation factuality rubric, and acceptance/learning-outcome dashboard. |

**DA first-sprint sample deliverable:** for a student at course 38 who failed
two checks on node 914, rank three eligible actions. Include the exact feature
values, rule/model score decomposition, reason codes, and outcome label window.
If the data cannot support a model, explicitly ship the calibrated rules
baseline rather than a misleading deep model.

## 9. DE work packages

DE owns durable contracts, ingestion, catalog/features, online serving,
observability, privacy controls and safe releases. DE does not decide learning
labels or tune model business objectives alone.

| ID | Task | Inputs | Required output / definition of done |
|---|---|---|---|
| DE-01 | Event contract and registry | §4, LMS/frontend/AI owners | Versioned JSON schema, compatibility policy, topic ACL/retention/partition plan, generated producer types for Go/TypeScript/Python and contract tests. |
| DE-02 | Instrumentation | frontend analytics, LMS handlers, chatbot cards | Producers for all mandatory events, particularly impression + recommendation metadata. Offline queue/retry; idempotent `event_id`; no raw message content. |
| DE-03 | Lakehouse pipeline | Kafka, current personalize service, contract | Bronze/Silver/Gold datasets in §7, dedupe/late event/backfill job, partitioning by event date/course where appropriate, quality dashboard and alerts. |
| DE-04 | Catalog and online feature snapshots | LMS course/section/content/quiz, AI mastery/profile | Publish/update stream and materialized online store. Point-in-time feature API/cache; eligibility checks resolve in bounded time. |
| DE-05 | `recommender-service` | DA model/policy artifact; catalog/features | Authenticated `POST /v1/recommendations`, response contract, generators, filter/ranker/policy composition, cache, fallback, tracking token signing, unit/integration/load tests meeting §5.4. |
| DE-06 | Recommendation ledger and analytics | returned recommendation sets; client outcomes | Append-only exposure/outcome join keys, model/policy audit table, dashboards for funnel, latency, fallback, duplicate/missing impression and cohort/slice monitoring. |
| DE-07 | Release, privacy and reliability | service and data pipeline | Model registry/version pinning, canary + rollback, kill switch, retention/access policy, on-call runbook and data deletion propagation. |

**DE first-sprint sample acceptance test:** submit a request for user 481 on
course 38; API returns only accessible published entities, each with a distinct
`recommendation_id`. Rendering the first card emits exactly one `impression`.
Clicking and completing the card joins to that exposure within the outcome
table. Replaying the same event does not duplicate it.

## 10. Shared acceptance metrics and experimentation

| Area | Offline before canary | Online guardrail / success criterion |
|---|---|---|
| Relevance | time-split Recall@K, NDCG@K, MRR vs `heuristic_v0` | accept/start rate by surface, compared to holdout |
| Learning | completion and 7-day mastery/assessment proxy | no decrease in course completion or quiz success; target lift agreed per course |
| Diversity/fairness | coverage, novelty, topic/level distribution, new-content exposure | no course/level cohort materially harmed; teacher-pinned content honoured |
| CRS | intent/constraint F1, factual explanation audit | clarification rate, edit/accept rate, user feedback; no unsupported explanations |
| Reliability | replay reproducibility, contract pass rate | p95 latency, fallback/error rate, Kafka consumer lag |

Evaluation uses temporal splits, never random interaction splitting: train on
events before a cutoff and test on later behaviour. Logged recommendation data
is exposure-biased; retain the control/holdout and propensities before making
causal claims.

## 11. Delivery plan

| Phase | Duration | Delivery gate |
|---|---:|---|
| 0 — contract and metrics | 1 week | DA-01 and DE-01 signed; event ownership map approved |
| 1 — trustworthy data and rules baseline | 2 weeks | DE-02/03, DA-02/03; complete exposure/outcome loop verified in staging |
| 2 — online NBA + chat integration | 2 weeks | DE-04/05/06; rules candidate service on one course/surface, HITL cards, SLO/load test |
| 3 — ranker + constrained roadmap | 2–3 weeks | DA-04/05; shadow scoring then 5% canary with rollback |
| 4 — experimentation and safe exploration | 2 weeks | DA-06/07, DE-07; propensity-valid logs, holdout, approved ramp |

Start with one well-instrumented course and one surface (lesson sidebar or
dashboard) before course discovery and cross-course models. A recommender with
clean outcomes on one course is far more valuable than a deep model fed by
ambiguous events across all courses.

## 12. Required reading and why it is assigned

1. Covington, Adams, Sargin, **Deep Neural Networks for YouTube
   Recommendations** — the candidate-generation/ranking separation that this
   design adopts. <https://research.google/pubs/deep-neural-networks-for-youtube-recommendations/>
2. Gomez-Uribe & Hunt, **The Netflix Recommender System: Algorithms, Business
   Value, and Innovation** — recommends a product/system view, not a
   single-algorithm view. <https://doi.org/10.1145/2843948>
3. Naumov et al., **Deep Learning Recommendation Model (DLRM)** — reference
   architecture for sparse/categorical + dense feature ranking at scale; a
   future option, not the v1 requirement. <https://arxiv.org/abs/1906.00091>
4. Li et al., **A Contextual-Bandit Approach to Personalized News Article
   Recommendation** — contextual exploration and offline evaluation from
   randomized/logged traffic. <https://arxiv.org/abs/1003.0146>
5. Jannach et al., **A Survey on Conversational Recommender Systems** — CRS
   intents, preference elicitation, feedback and evaluation. <https://arxiv.org/abs/2004.00646>
6. Li et al., **A Conversation is Worth A Thousand Recommendations** — why
   real multi-turn dialogue needs external knowledge/guidance and holistic
   evaluation. <https://arxiv.org/abs/2309.07682>
7. Piech et al., **Deep Knowledge Tracing** — connects student interaction
   history to mastery-aware curriculum decisions. <https://arxiv.org/abs/1506.05908>
8. Oosterhuis & de Rijke, **Unifying Online and Counterfactual Learning to
   Rank** — position/selection bias and intervention-aware evaluation.
   <https://www.ijcai.org/proceedings/2021/656>

## 13. Explicit non-goals for v1

- No autonomous enrollment, content modification, teacher grading, or learner
  profile change from a chat response.
- No end-to-end deep/RL model before event quality, baseline, and outcome
  logging are proven.
- No training on raw chat text by default; use de-identified intent and explicit
  structured constraints with a documented consent/retention policy.
- No metric claiming that recommendation caused learning without a suitable
  holdout or counterfactual design.

