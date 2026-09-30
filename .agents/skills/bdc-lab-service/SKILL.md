---
name: bdc-lab-service
description: Lab service guidance for Go/Gin labs, submissions, execution adapters, Kafka job contracts, and sandbox safety.
triggers: [lab-service, coding-lab, submission, runner, sandbox, lab-job]
version: "3.0"
requires: [bdc-core-orchestrator]
---

# BDC Lab Service

## Scope

`lab-service/cmd/api/main.go` composes the API. The service owns labs,
test-cases, submissions, leaderboard state, and execution adapters in
`internal/runtime/`. Its Kafka constants live in `pkg/kafka/events.go`.

## Rules

- Treat submitted code and execution output as untrusted. Preserve time, memory,
  filesystem, network, process, and output limits in the execution boundary.
- Enforce lab/course/enrolment/role checks before exposing a test case, accepting
  a submission, or publishing a result. Never reveal hidden test data.
- Do not claim `lab.job.*` or session topics are product-ready without verifying
  producer, consumer/runner, failure handling, and observability. Update the
  Data Platform guide for any contract implementation.
- Keep submission/result transitions idempotent and auditable. Use forward-only
  migrations and parameterised persistence.
- Run `go test ./...`; add tests for authorization, dangerous input/limits,
  runner timeout/error, and duplicate job/result handling.
