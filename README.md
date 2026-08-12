# BDC Hub CoreApplication

BDC Hub is an AI-assisted learning platform. This repository contains the
backend services, Kubernetes manifests, local Compose environments,
performance-test assets, and the Data Analytics submodule. The frontend is a
Git submodule and has its own contribution rules.

## Start here

| Audience | Read first | Primary assets |
|---|---|---|
| Business analyst / product | [BA handbook](docs/teams/BA_HANDBOOK.md) | journeys, acceptance criteria, event impacts |
| Application developer | [Developer guide](docs/DEVELOPER_GUIDE.md) and [Kubernetes quick start](docs/KUBERNETES_DEVELOPER_GUIDE.md) | service map, local workflow, infrastructure layers, K3s inspection and sandbox start |
| Data analyst / data engineer | [Data platform guide](docs/DATA_PLATFORM.md) | Lakehouse layers, Kafka catalog, data quality |
| DevOps / SRE | [DevOps runbook](docs/DEVOPS_RUNBOOK.md) | K3s, CI/CD, rollback and performance operations |
| QA / performance | [Performance tests](performance-tests/README.md) | k6 scripts, safety gates and dashboard flow |
| Any contributor | [Contributing guide](CONTRIBUTING.md) | branches, review, tests, documentation governance |

[Team assets index](docs/TEAM_ASSETS.md) is the canonical catalogue of
repositories, dashboards, manifests, APIs, test assets, and ownership.

## Platform at a glance

```text
Browser
  |
  v
Frontend (Next.js submodule) -- HTTP --> Auth / LMS / Lab / Chat / AI / Recommender
                                                |                 |
                                                +---- Kafka ------+
                                                       |
                                                       v
                                          Personalize Lakehouse (DuckDB + Parquet)

Production: K3s + Traefik + Kafka + Redis
Local:      Docker Compose (self-hosted or serverless dependencies)
```

| Boundary | Directory | Runtime responsibility |
|---|---|---|
| Frontend | `frontend/` (submodule) | Next.js UI, browser authentication, API proxy routes |
| Identity | `auth-and-management-service/` | Spring Boot auth, user and organisation management |
| Learning | `lms-service/` | Go/Gin courses, content, quizzes, progress, analytics events |
| Lab | `lab-service/` | Go/Gin coding labs, submissions and runners |
| Chat | `chat-service/` | Go/Gin WebSocket chat and persistence |
| AI | `ai-service/` | FastAPI, RAG, graph, quiz/flashcard/mentor workflows and Kafka worker |
| Personalization | `personalize-service/` | DuckDB Lakehouse, learner profile and struggle signals |
| Recommendations | `recommender-service/` | Low-latency rules slate, signed tracking and outcome events |
| Platform | `k3s/`, `.github/`, `scripts/` | Kubernetes manifests, automation and deployment scripts |

Each service owns its persistent data. Do not query or mutate another service's
database directly; use its API or a documented event contract.

## Repository layout

```text
.
├── auth-and-management-service/  Spring Boot identity and management API
├── lms-service/                  Go learning API and Kafka producers/consumers
├── lab-service/                  Go lab API and execution boundary
├── chat-service/                 Go WebSocket chat API
├── ai-service/                   FastAPI + AI Kafka worker
├── personalize-service/          DuckDB Lakehouse and profile worker
├── recommender-service/          Recommendation serving API
├── frontend/                     Git submodule
├── da-analytics/                 Git submodule for offline DA/ML work
├── k3s/                          Kustomize base, observability and Helm values
├── performance-tests/            k6 scripts and Kubernetes Jobs
├── docs/                         Curated operating and team documentation
├── .agent/skills/                Repository-specific agent guidance
└── docker-compose*.yml           Local runtime variants
```

## Local development

1. Clone with submodules and create local configuration without putting secrets
   in Git:

```bash
git clone --recurse-submodules <repository-url>
cd CoreApplication
cp .env.example .env
git submodule update --init --recursive
```

2. Fill only the local values required by the services you run. `.env` is
   ignored. Never copy production secrets into it.

3. Validate the chosen Compose definition, then start the stack:

```bash
docker compose config
docker compose up --build
```

`docker-compose.yml` provides local stateful dependencies. Use
`docker-compose.serverless.yml` only when the approved external dependency
configuration is available. See the developer guide for focused service runs
and test commands.

## Documentation governance

The documents above describe the current implementation. Source code,
Kubernetes manifests, and GitHub workflows are authoritative when a discrepancy
is found. Update the relevant document in the same pull request as any change
to an API, Kafka payload, Lakehouse table, deployment path, or user-visible
behaviour.

Historical migration instructions, duplicate CI/CD guides, speculative
recommender briefs, and stale slide/PDF material were removed in the
documentation consolidation. Architecture decisions remain in [docs/adr](docs/adr/).

## Contribution

Read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request. In
particular, event and data changes require both a contract update and an
integration/compatibility test; production deployment must use immutable image
SHAs, never a mutable tag.
