# ADR-5: Evidence-grounded Agentic Platform Foundation

## Status

Accepted - 2026-07-30.

## Context

BDC needs a course-aware Virtual TA for both teachers and students. It must
understand the authenticated role, current course/section/content, learning
state and teacher intent; safely create drafts and recommendations; and remain
fast under provider token-per-minute limits. The earlier implementation had
useful tools, GraphRAG and a three-tier memory, but multi-agent execution was a
fixed Retrieval → Draft → Critique pipeline and durable session memory was an
unattributed JSON summary.

## Decision

### 1. Context and evidence

- UI context is a hint and is verified against the user's active course access.
- Knowledge-graph nodes represent teachable concepts only. Figures, plots and
  other artifacts stay retrievable in RAG but do not become curriculum nodes.
- Large documents use coverage-preserving hierarchical reduction; no request
  path is allowed to silently slice source material to fit an LLM context.
- The LLM gateway owns model/key selection, telemetry and token preflight.

### 2. Memory

Memory is tiered and bounded:

- STM: recent dialogue only, within a strict token budget.
- MTM: compact session state and `MemoryItem` records.
- LTM: retrieved episodes and measured learning signals.

`MemoryItem` has `kind`, `value`, `scope` (session/course/user), `confidence`,
`status` (active/completed/superseded), `source`, and optional `course_id`.
Only active, in-scope, high-priority memory is injected into a prompt. Existing
MTM summaries migrate lazily to this model.

### 3. Multi-agent protocol

Specialists exchange bounded, attributable artifacts rather than full chat
transcripts. The common contracts are:

`AgentTask → OrchestrationPlan(capability DAG) → AgentArtifact → HITL action`.

Capabilities are registered independently of the orchestrator. The current
platform registers evidence retrieval, response drafting and quality critique;
the policy selects the smallest available DAG per task. Future capabilities
(research, code execution, assessment review, data analysis) can register
without replacing orchestration control flow.

### 4. Human-in-the-loop and side effects

- Teacher content, quiz and course mutations are always drafts first.
- Teachers can edit title, description, content, questions and course location
  in the approval UI before the LMS action executes.
- Authoring requests bypass prose-only multi-agent mode, ensuring they reach
  the tool-capable workflow and do not lose the approval step.

### 5. Instructional model

Lesson generation accepts learner profile, goals, duration, pedagogical mode
and teacher constraints. It produces a learner-facing draft plus an editable
learning-design contract: objectives, prerequisites, approach, practice type,
extension, research directions and evidence limits. Quiz generation receives
assessment purpose and teacher constraints, then aligns questions with Bloom
level and retrieved source evidence.

## Consequences

- Lower token/cost risk and less context contamination.
- Clear traceability for memory, graph and generated educational artifacts.
- More specialists can be added incrementally without a hard-coded supervisor.
- Existing course actions remain safe because approval is explicit.

## Research basis

- MemGPT: virtual-context management for long-running LLM agents.
- AutoGen: agent collaboration through explicit roles/messages.
- LLMCompiler: task dependency graphs and parallelizable agent execution.
- Reflexion: quality feedback as a bounded improvement loop rather than hidden
  unbounded reasoning.
