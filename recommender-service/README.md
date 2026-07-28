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
