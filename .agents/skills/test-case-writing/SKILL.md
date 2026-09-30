---
name: bdc-test-writing
description: Test design and implementation for BDC services, covering authorization, contracts, migrations, Kafka idempotency, and production safety.
triggers: [test, unit-test, integration-test, pytest, junit, go-test, contract-test, regression]
version: "3.0"
requires: [bdc-core-orchestrator]
---

# BDC Test Writing

## Baseline

Write deterministic tests for behaviour owned by the changed service. Use the
existing framework and test conventions in that service; do not assume a common
coverage threshold is currently enforced unless the workflow proves it.

## Required cases where relevant

- Success path, validation failure, unauthenticated, forbidden, and not-found
  behaviour for API changes.
- Regression reproduction for a bug fix.
- Transaction/migration compatibility and data ownership for persistence work.
- Duplicate, malformed, late, and dependency-failure delivery for Kafka/event
  work; assert idempotent results.
- Fallback and timeout behaviour for AI/profile/recommendation dependencies.
- Permission and human-approval controls for agent/content-changing workflows.

## Commands

- Java Auth: `mvn test` from `auth-and-management-service/`.
- Go services: `go test ./...` from the affected service directory.
- AI/Python services: `python -m pytest` where tests exist; add focused pytest
  coverage with new Python behaviour.
- Compose/Kubernetes/documentation changes: validate configuration/link syntax
  in addition to application tests.

Never place credentials, live user data, or mutable production dependencies in a
unit test. Use isolated fixtures and record external dependencies that cannot be
covered locally.
