---
name: bdc-ai-service
description: AI service and worker guidance for FastAPI, RAG, graph, agent tools, and Kafka-driven jobs.
triggers: [ai-service, fastapi, ai-worker, rag, qdrant, neo4j, flashcard, quiz, agent]
version: "3.0"
requires: [bdc-core-orchestrator]
---

# BDC AI Service

## Scope

`ai-service/main.py` is the FastAPI boundary. `app/worker/kafka_worker.py` is
the asynchronous worker. They share an image but are separate workloads in
production. Inspect `app/core/config.py`, endpoint router registration, and the
specific service before changing behaviour.

## Rules

- Keep expensive model, indexing, document, or graph work in the worker. Return
  an observable job/status contract from HTTP triggers.
- Current worker inputs include `lms.document.uploaded`, `lms.graph.command`,
  `lms.maintenance.command`, `lms.ai.command`, and
  `personalize.profile.updated`. Outputs are implemented in
  `app/worker/kafka_producer.py`. Update `docs/DATA_PLATFORM.md` with any
  contract change.
- Reuse configured client/model factories and connection lifecycles. Do not
  instantiate hidden global LLM, embedding, Qdrant, Neo4j, or database clients.
- Preserve authorization and human approval for content-changing agent actions.
  An agent tool may prepare a draft; it must not bypass LMS permissions.
- Make worker handlers idempotent, observable, timeout-aware, and safe to retry.
- Add pytest coverage for parsing, authorization, failure, and duplicate-event
  behaviour relevant to the change.

## References

- `app/agents/` — agent routing, context and tools.
- `app/services/` — RAG, graph and domain services.
- `app/worker/` — consumer/producer contracts.
- `docs/adr/` — accepted AI/graph/context decisions.
