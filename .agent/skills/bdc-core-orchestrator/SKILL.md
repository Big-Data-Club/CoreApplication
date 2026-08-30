---
name: bdc-core-orchestrator
description: Repository-wide BDC Hub constraints, service ownership, runtime topology, CI/CD, data contracts, and safe change workflow.
triggers: [architecture, cross-service, k3s, docker-compose, kafka, lakehouse, ci-cd, deployment]
version: "3.0"
---

# BDC Hub Core Context

## Load order and scope

Load this skill before a service-specific BDC skill whenever a task affects more
than one service, Kafka, Lakehouse, Compose, K3s, CI/CD, or shared
configuration. Treat source code, `k3s/`, `.github/workflows/`, and current
team documents as authoritative; do not rely on historical assumptions.

## Current topology

- Production runs on K3s with Traefik, Kafka and Redis. Local development uses
  `docker-compose.yml`; `docker-compose.serverless.yml` is an external-dependency
  variant.
- `frontend/` and `da-analytics/` are Git submodules; follow their own rules.
- Application boundaries: Auth, LMS, Lab, Chat, AI HTTP/worker, Personalize,
  and Recommender. Each service owns its persistent data.
- Long AI/indexing work belongs on the Kafka worker, not a request handler.
- The current production workflow is `.github/workflows/production.yml`; it
  deploys only selected AI/Recommender/Personalize/LMS paths. A green no-change
  run is not a deployment. Read `docs/DEVOPS_RUNBOOK.md` before changing it.

## Non-negotiable rules

1. Never commit or expose credentials, real user data, `.env`, test account
   passwords, internal tokens, or production host details.
2. Never read/write another service's database. Use an authenticated API or a
   documented Kafka event.
3. Treat Kafka as at-least-once: stable keys, event IDs, idempotent consumers,
   compatible payload evolution, and explicit failure behaviour are mandatory.
4. Validate authenticated identity/role/resource scope server-side. Browser
   IDs are input, not authority.
5. Add forward-only migrations; do not rewrite deployed migrations.
6. Update `docs/DATA_PLATFORM.md`, `docs/DEVELOPER_GUIDE.md`,
   `docs/DEVOPS_RUNBOOK.md`, or the BA handbook whenever their stated boundary
   changes. Use an ADR for durable architecture decisions.

## Required pre-merge checks

- Run the affected service test suite and `git diff --check`.
- Validate Compose/Kustomize when their files change.
- For event/data changes, add a compatibility or integration test and document
  rollout order, privacy purpose, producer, consumer, and failure mode.
- For deployment/performance work, follow the production runbook and approved
  performance procedure; do not run stress traffic from an application node.

## Primary references

- `README.md` - repository map and team entry points.
- `CONTRIBUTING.md` - PR and change rules.
- `docs/DATA_PLATFORM.md` - Lakehouse/topic source of truth.
- `docs/TEAM_ASSETS.md` - owner and asset catalogue.
- `docs/DEVOPS_RUNBOOK.md` - K3s and CI/CD operations.
