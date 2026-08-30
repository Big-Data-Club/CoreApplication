---
name: bdc-lms-service
description: LMS service guidance for Go/Gin learning APIs, PostgreSQL, Redis, content/progress, and Kafka boundaries.
triggers: [lms-service, golang, gin, course, quiz, progress, learning, micro-interaction]
version: "3.0"
requires: [bdc-core-orchestrator]
---

# BDC LMS Service

## Scope

`lms-service/cmd/api/main.go` composes the Go/Gin API. `internal/` contains
handlers, services, repositories, models and DTOs; `pkg/kafka/` contains the
current event types/consumers; `migrations/` is the forward-only database
history.

## Rules

- Keep handlers focused on HTTP binding/auth/context; put domain rules in
  services and persistence in repositories. Use parameterised SQL and request
  contexts/timeouts.
- Enforce LMS authorization against the authenticated subject and owned course
  or organisation scope. Never rely solely on a supplied user/course ID.
- Async AI requests publish compatible job/document/maintenance events and
  expose recoverable status. Do not wait for long AI work in an HTTP request.
- `lms.analytics.interactions` is a product/data contract. Preserve
  `interaction_id` idempotency and course-key ordering; update the Data Platform
  guide and tests before changing it.
- Add a new migration rather than modifying an existing one. Test with
  `go test ./...` and update Swagger/generated docs if the project workflow
  requires it.

## References

- `pkg/kafka/events.go` - implemented LMS event shapes.
- `pkg/kafka/consumer.go` - status/graph/micro-interaction consumers.
- `docs/DATA_PLATFORM.md` - full current topic catalogue.
