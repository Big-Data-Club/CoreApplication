# Contributing to BDC Hub CoreApplication

## Scope and safety

Contributions must preserve service ownership, backward compatibility, and the
production safety rules in the [DevOps runbook](docs/DEVOPS_RUNBOOK.md).
Do not commit credentials, production data, exported user data, `.env` files,
or generated model artifacts. Use test accounts and an isolated Test Course for
end-to-end and performance testing.

The repository has two submodules: `frontend/` and `da-analytics/`. Work inside
their repositories only when the change belongs there. Commit that work in the
submodule first, then update the pointer in this repository in a separate,
reviewable change.

## Before coding

1. Read the team guide for the affected boundary and inspect the current source
   code, migrations, manifests, and tests.
2. Create a short-lived branch from the current integration branch. Do not push
   directly to `main`.
3. Define acceptance criteria, authorization behaviour, data ownership, and
   failure/rollback behaviour before introducing a new endpoint, event, or job.
4. For cross-service work, agree the payload/schema and rollout order with the
   affected owners first.

## Local setup

```bash
git submodule update --init --recursive
cp .env.example .env
docker compose config
```

Use placeholders or local-only credentials in `.env`; it is intentionally
ignored by Git. Start only the services required for the change where possible.

## Change rules

### Application code

- Keep request handlers/controllers thin; put domain logic in the established
  service/repository layer for that service.
- Validate input, authenticate, authorize, and return consistent error status
  codes before adding a new mutation.
- Add migrations as new, forward-only files. Do not rewrite migrations that may
  already have been applied outside a local database.
- Do not access another service's database. Use an owned API or Kafka event.
- Keep expensive AI/document operations asynchronous. The HTTP boundary should
  return a durable job reference or explicit failure, not hold a request open.

### Kafka and Lakehouse changes

- Use a versioned topic for a new independent contract (for example
  `domain.entity.event.v1`); do not silently change an existing payload.
- Include a stable event ID, event time, aggregate/user key, and enough context
  for an idempotent consumer. Key events by the ordering boundary, normally
  `user_id:course_id` for learning/recommendation events.
- Consumers must tolerate duplicate delivery, unknown additive fields, and
  temporary broker failure. Do not make a learner-facing action fail only
  because analytics publication failed unless the product explicitly requires
  it.
- Update [Data platform guide](docs/DATA_PLATFORM.md), add contract tests, and
  state producer/consumer rollout order in the PR.

### Documentation and agent skills

- Update the relevant team guide whenever user behaviour, API surface, topic,
  table/view, operational command, or deployment path changes.
- Keep `.agent/skills/` concise and implementation-backed. Skills must point to
  source-of-truth files and must not contain credentials, environment-specific
  hostnames, or invented APIs.
- Add an ADR in `docs/adr/` for a durable, cross-cutting architectural decision;
  do not use an ADR for a routine implementation detail.

## Required verification

Run the narrowest relevant checks first, then the service suite before review.

| Area | Baseline command |
|---|---|
| Auth service | `cd auth-and-management-service && mvn test` |
| Go services | `cd <service> && go test ./...` |
| AI service | `cd ai-service && python -m pytest` |
| Python service with tests | `cd <service> && python -m pytest` |
| Compose changes | `docker compose config` |
| Kubernetes YAML | `kubectl kustomize k3s/base` |
| Documentation | `git diff --check` and verify all changed links |
| Performance-sensitive path | Follow `performance-tests/README.md`; smoke only unless explicitly approved |

Record commands actually run and any skipped checks in the pull request. A
failed or unavailable integration dependency is not a reason to mark a feature
complete without noting the limitation.

## Pull request checklist

- [ ] Problem, scope, and acceptance criteria are clear.
- [ ] No secret, production data, or generated local artifact is included.
- [ ] Tests cover the changed behaviour and regression risk.
- [ ] API, event, schema, or Lakehouse documentation is updated where relevant.
- [ ] Database migration is forward-only and has an operational rollback plan.
- [ ] Kafka producer/consumer compatibility and deployment order are documented.
- [ ] CI status is interpreted correctly: a green no-change workflow is not a
      release; see the DevOps runbook.
- [ ] Reviewer can reproduce the verification commands.

## Review and release

At least one appropriate owner reviews the change: product/BA for behaviour,
service owner for code, data owner for analytics contracts, and DevOps for
manifest or deployment changes. Merge only after required checks pass.

`production.yml` deploys a limited, selected matrix from `main`; it does not
deploy every service for every change. Release operators must verify the
immutable image SHA and Kubernetes rollout as documented in the runbook.
