# BDC Hub Developer Guide

## 1. Working model

BDC Hub is a service-oriented learning platform. Production runs on K3s;
Docker Compose is for local development. Each service owns its data and public
behaviour. Cross-service operations use authenticated APIs or versioned Kafka
events, never direct database access.

| Service | Stack | Main entry point | Owns |
|---|---|---|---|
| Auth | Java / Spring Boot | `auth-and-management-service/` | identity, roles, organisations |
| LMS | Go / Gin | `lms-service/cmd/api/main.go` | course/content/progress/quiz state |
| Lab | Go / Gin | `lab-service/cmd/api/main.go` | coding labs and submissions |
| Chat | Go / Gin | `chat-service/cmd/api/main.go` | chat HTTP/WebSocket state |
| AI HTTP + worker | Python / FastAPI / aiokafka | `ai-service/main.py`, `app/worker/kafka_worker.py` | AI, RAG, graph and async jobs |
| Personalize | Python / DuckDB / aiokafka | `personalize-service/main.py`, worker | learner analytics and profiles |
| Recommender | Python / FastAPI | `recommender-service/app/` | fast recommendations and outcome capture |
| Frontend | Next.js submodule | `frontend/` | browser UX and server-side proxy boundary |

## 2. First local run

```bash
git submodule update --init --recursive
cp .env.example .env
docker compose config
docker compose up --build
```

Use `.env.example` as a list of required configuration names, not as a source of
production values. Keep `.env` local. For a focused change, start only the
needed dependencies/service with Compose and use the service's own `.env.example`
as reference.

`docker-compose.yml` includes local stateful dependencies. The serverless
variant expects approved external service configuration; do not use it as a
shortcut around local setup.

## 3. Service change workflow

1. Locate the owning service and read its config, entry point, migration folder,
   routes, and existing tests.
2. Define the request/response or event contract first. Identify role checks,
   validation, idempotency, and failure behaviour.
3. Implement within the service's established layering. Add a forward-only
   migration if persistent schema changes.
4. Add unit/integration coverage and run the relevant service tests.
5. Update the product, data, operations, and agent-skill documents affected by
   the change.
6. Open a PR with exact verification commands, compatibility/rollout order, and
   any untested dependency.

## 4. Non-negotiable boundaries

### Data and authentication

- Auth is authoritative for identity. LMS uses an authenticated user-sync
  boundary; it is not a substitute for a cross-service database join.
- Never read/write another service's database or storage schema directly.
- Do not trust browser-provided user, role, course, or organisation IDs without
  verification against the authenticated server-side authority.
- Keep secrets in runtime configuration or Kubernetes Secrets. Never log them,
  embed them in tests, or add them to documentation.

### AI and asynchronous work

- Long-running document processing, model calls, indexing, and batch graph work
  belong in the AI worker. HTTP triggers should return a job reference and
  observable status rather than wait indefinitely.
- Kafka is at-least-once delivery. Consumers must be idempotent and producers
  must use a stable message key.
- Keep AI output behind existing authorization and human-approval controls;
  generation alone is not authorisation to publish or mutate learning content.

### API and database changes

- Preserve compatible request/response fields. Additive changes are preferred;
  breaking changes require an explicit version/migration plan.
- Use parameterised queries and context/timeouts. Do not construct SQL with
  string interpolation.
- New migrations must be forward-only, reviewed for lock/size impact, and
  accompanied by an operational recovery plan.

## 5. Kafka, Lakehouse, and recommendations

Read [DATA_PLATFORM.md](DATA_PLATFORM.md) before touching a producer, consumer,
analytics event, recommendation outcome, or DuckDB table. Minimum requirements:

- A topic payload has an event ID, event time, key/ordering boundary and
  compatibility rule.
- The consumer tolerates duplicate and late delivery.
- Analytics publication does not turn an otherwise successful learner action
  into a failed request unless that is an explicit product requirement.
- New fields have a data purpose, access/retention decision, documentation, and
  contract test.

## 6. Tests and checks

| Change | Run before review |
|---|---|
| Auth | `cd auth-and-management-service && mvn test` |
| LMS, Lab, Chat | `cd <service> && go test ./...` |
| AI | `cd ai-service && python -m pytest` |
| Personalize/Recommender | `cd <service> && python -m pytest` when tests exist; add tests for new behaviour |
| Compose | `docker compose config` |
| Kubernetes | `kubectl kustomize k3s/base` |
| Documentation | `git diff --check`, then validate edited relative links |

For a production performance-sensitive path, do not improvise load. Start with
the approved k6 smoke profile and guardrails in `performance-tests/README.md`.

## 7. CI/CD expectations

`production.yml` is the SHA-based production path on `main`, but it has a
selected-service matrix. A green workflow may be an intentional no-op when no
watched path changes. `ci.yml` is quality CI for its configured branches, while
`cd-production.yml` is a legacy restart path. The exact current states and
required verification are maintained in the [DevOps runbook](DEVOPS_RUNBOOK.md).

Never label a build as deployed until the immutable image SHA and Kubernetes
rollout have both been checked.

## 8. Documentation and skills

Use [Team assets](TEAM_ASSETS.md) to find the applicable owner and document.
The `.agent/skills/` files are concise repository instructions for coding
agents; update them when a service boundary, deployment topology, or contract
changes. Do not duplicate long API references in skills.

For contribution mechanics, PR checklist, migrations, event compatibility, and
submodule rules, follow [CONTRIBUTING.md](../CONTRIBUTING.md).
