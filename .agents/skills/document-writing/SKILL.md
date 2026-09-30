---
name: bdc-documentation
description: Documentation maintenance for BDC Hub, including source-of-truth, team handoffs, operational accuracy, and link hygiene.
triggers: [documentation, readme, handbook, adr, runbook, kafka-contract, lakehouse]
version: "3.0"
requires: [bdc-core-orchestrator]
---

# BDC Documentation

## Standard

Write concise, implementation-backed Markdown. Use Vietnamese for BA/product
handoffs when the delivery team needs it; use clear technical English for shared
engineering/operations documents unless the requester specifies otherwise.
Avoid credentials, environment-specific access data, and absolute local file
links.

## Rules

1. Identify the document owner and source-of-truth code/configuration before
   writing. State current implementation separately from planned work.
2. Keep one canonical document per operational subject. Replace stale duplicates
   rather than creating competing guides; retain ADRs as decision history.
3. Update docs in the same PR as API, topic, Lakehouse, deployment, user-flow,
   or contribution-process changes.
4. Link with repository-relative Markdown paths; verify every changed link and
   run `git diff --check`.
5. For Kafka/Lakehouse docs, include producer, consumer, owner, idempotency,
   compatibility, data purpose, and rollout/rollback implications.
6. For operational docs, distinguish observed state, safe commands, and actions
   that require approval. Do not claim a green CI run implies deployment.

## Canonical locations

- `README.md` - repository entry point.
- `CONTRIBUTING.md` - contributor process.
- `docs/teams/BA_HANDBOOK.md` - BA/product handoff.
- `docs/DEVELOPER_GUIDE.md` - implementation workflow.
- `docs/DATA_PLATFORM.md` - Kafka and Lakehouse.
- `docs/DEVOPS_RUNBOOK.md` - production operations.
- `docs/TEAM_ASSETS.md` - team asset index.
- `docs/adr/` - durable architecture decisions.
