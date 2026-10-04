# ADR-6: Bounded Jev planner acceleration

## Status

Implemented behind an off-by-default flag, 2026-10-04. Production activation
and performance/semantic validation remain rollout work.

## Context

The unified LLM planner owns more than intent classification: page relevance,
retrieval scope, selected tools, clarification, graph and learner signals.
Replacing it wholesale risks losing lesson context or routing draft requests
into prose-only workflows. The existing Jev decision only promotes borderline
Deep questions to retrieval/draft/critique and must remain compatible.

## Decision

Add a standard-mode entry point after deterministic context resolution. Permit
one code-owned course QA template for standalone mentor questions with one
resolved active course and no history/page/system context. Keep every existing
downstream authorization, clarification and tool-execution check.

Extend the managed System One adapter with bounded, named boolean questions.
Validate every requested answer as a finite probability; preserve raw precision
for threshold decisions. Reject oversized custom states instead of truncating.
Keep the existing decomposition API/response and MCP assessment unchanged.

The new adapter is internal: callers own the questions; user text cannot
define tools, permissions, questions or plan fields. Do not add a public generic
decision endpoint. The gateway still owns provider selection, keys and usage.

Use off/shadow/active modes and a total deadline. Shadow returns the original
plan, records field differences and cancels unfinished work. Active rejects
uncertain/invalid/unavailable decisions and falls back with full original
inputs. No shared decision cache is introduced, avoiding stale authorization
and cross-user context reuse.

## Consequences and validation

An accepted decision saves one planner completion, not the entire ReAct loop.
Fallback adds latency up to the decision budget plus cancellation cleanup.
Coverage is intentionally low initially; model scores are not proof of safety
or domain calibration. The lexical exclusions are conservative optimizations,
not security filters. Tool permissions remain enforced at execution.

Unit/regression coverage must verify disabled behavior, eligibility exclusions,
mixed actions, malformed probabilities, precision at thresholds, provider
failure, total timeout, shadow cancellation, request cancellation, template
scope, unchanged decomposition behavior and configuration bounds.

Before active rollout, evaluate labelled Vietnamese/English requests and
review all false accepts, especially action/scope/personalization requests.
Require no observed authorization or approval regressions, no degradation on
the agreed grounding/routing evaluation, and measured latency/cost benefit on
the eligible cohort. Assess fallback-inclusive p95, not just accepted requests.
These are release criteria, not claims established by mocked unit tests.

## Future extensions

Auto-index remains extract → concepts → dedup → chunks → graph. Micro-lessons
remain source-grounded generation ordered by prerequisites. Their worker/event
contracts are unchanged by this decision.

Later policies may evaluate extraction quality or lesson outline adequacy using
this adapter. Each needs its own versioned criteria, evidence-bearing bounded
state, labelled evaluation, retry budget and fallback before activation.
Document skipping, concept deletion/merge and publication must not be delegated
to a probability threshold. Long processing remains in the Kafka worker.

Operational flags, observation fields and rollback are described in
[LLM gateway operations](../llm-gateway-operations.md#bounded-standard-chat-planner-accelerator).
