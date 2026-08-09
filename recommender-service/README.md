# BDC Recommender Service

Online serving boundary for BDC learning recommendations. It is intentionally
small and fast: retrieve the cached learner profile from `personalize-service`,
apply eligibility-safe rules, issue a signed tracking token, and publish
exposure/outcome events to Kafka. It does not call an LLM on the request path.

## Internal API

All endpoints except `/health` require `X-AI-Secret`.

- `POST /v1/recommendations` — returns a ranked, explainable next-action slate.
- `POST /v1/events` — accepts idempotent impression/click/accept/reject/start
  events. The token binds the event to the original user and recommendation.

The Next.js `/api/recommendations*` routes own browser authentication and inject
the user identity server-side. Browsers never receive the internal secret.

## Environment

| Variable | Default | Purpose |
|---|---|---|
| `PERSONALIZE_SERVICE_URL` | `http://personalize-service:8082` | profile lookup |
| `KAFKA_BROKERS` | `kafka:9092` | outcome event publishing |
| `AI_SERVICE_SECRET` | — | internal authentication and v1 token key fallback |
| `TRACKING_SECRET` | empty | optional independent HMAC key |

If profile retrieval fails, the service returns an explicit `fallback: true`
rules slate rather than delaying the user-facing action.

## Hybrid course ranking

`hybrid-rules-v2` supports course ranking on `dashboard` and
`course_discovery`. The authenticated surface supplies an eligibility-safe
`candidates` array; LMS remains the authority for course visibility and
enrollment. The recommender never grants access to a candidate.

Discovery combines explicit goal/category match, level fit, quality-adjusted
popularity, freshness and stable exploration. With no explicit profile it uses
the latter four signals as a deterministic cold-start policy and marks the
response as `fallback: true`.

When the request does not carry explicit preferences, the service reads the
learner onboarding profile from `personalize-service`. Explicit request context
wins, which lets a learner's just-saved preferences affect the next slate
without waiting for the short profile cache to expire. Discovery slates also
apply a category repetition penalty after base scoring.

Dashboard ranking excludes completed/unenrolled candidates and combines
continuity, completion momentum, verified new-content counts, goal match and
freshness. LMS computes `new_content_count` from published content created
after the learner's latest completion (or enrollment when no content has been
completed). Badges such as `new_content` are only emitted for that
source-grounded count; the recommender does not infer or generate this claim.
