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

For each ReAct call, the gateway computes the usable request budget from the
selected model's context window, the selected key's TPM tier, and the configured
safety ratio. The agent reserves output space, then packs recent dialogue and
tool evidence into the remaining input space. Tool calls and their results stay
paired; omitted evidence is explicitly marked and can be retrieved again.
If the full teaching policy itself exceeds a small tier, the agent uses a
separately authored compact policy retaining role, grounding, citation and
draft-approval rules. Lower-priority tool definitions can then be deferred;
the active user request is never dropped. The gateway copies tool metadata
per key attempt, so reducing a prompt for one key does not weaken later
attempts on a larger tier.
Memory uses a fraction of that live input budget, so a small binding recalls
less while a larger binding can carry more. A request that cannot fit its
system instructions, active user question and tool schema fails preflight; the
gateway tries another eligible key on that model, then the next binding.

After a completed turn, the agent increments the session turn count. Every
`CONSOLIDATION_TURN_INTERVAL` turns, or when Redis STM crosses
`STM_OVERFLOW_THRESHOLD`, it publishes a Kafka job containing session identity
and scope only. The worker reads at most 100 new messages at a time from the
durable transcript, merges bounded summaries into MTM, advances a message-ID
cursor, and trims Redis to six recent messages. LTM receives only compact
episode summaries, with a stable episode ID for job retries. Retrieval of LTM
episodes or learner facts is optional and independently budgeted; graph/vector
search is never a reason to inject every hit into the model context.

Output continuation is a separate bounded policy: `AGENT_MAX_ANSWER_CONTINUATIONS`
defaults to three extra calls (four calls total), while
`AGENT_MAX_CONTINUATION_TOKENS` caps estimated visible answer size. Deep uses
separate defaults: `AGENT_DEEP_MAX_ANSWER_CONTINUATIONS=12`,
`AGENT_DEEP_MAX_ANSWER_TOKENS=24000`, and
`AGENT_DEEP_ANSWER_CHUNK_TOKENS=4096`. The shared completion policy covers
ReAct answers, final synthesis after tools, and each multi-agent draft/revision.
Continuation stops as soon as the provider reports completion, makes no new
progress, or reaches the budget. Interrupted streams get at most two recovery
attempts, within the same call budget. Unfinished output is persisted and
reported as incomplete. These limits are operational controls, not properties
of a particular provider. See the gateway operations guide for details.

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
