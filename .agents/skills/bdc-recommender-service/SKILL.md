---
name: bdc-recommender-service
description: Recommender service guidance for low-latency profile lookup, rules slates, tracking-token validation, fallback, and outcome events.
triggers: [recommender-service, recommendation, ranking, tracking-token, personalization]
version: "3.0"
requires: [bdc-core-orchestrator]
---

# BDC Recommender Service

## Scope

The recommender is an online serving boundary. It retrieves the learner profile
from Personalize, returns an explainable rules-based action slate, validates a
signed tracking token, and publishes `recommender.interactions.v1` outcomes.
It must not put an LLM or offline training job on the user request path.

## Rules

- Preserve low-latency fallback: a profile lookup failure returns an explicit
  fallback slate rather than failing a learner action or waiting unboundedly.
- Validate user identity and tracking token server-side. Do not expose the
  internal secret/token-signing material to browser code or logs.
- Event publication should be idempotent through `event_id`; analytics failure
  should be observable but must not invalidate an otherwise accepted human
  action unless product requirements explicitly say so.
- Keep recommendation reasons factual, bounded, and compatible with the
  authorised course/role scope. Do not imply model-based precision when the
  current implementation is a rules baseline.
- Update `docs/DATA_PLATFORM.md` for payload/profile changes and add pytest
  coverage for fallback, invalid token, duplicate event, timeout, and role
  handling.
