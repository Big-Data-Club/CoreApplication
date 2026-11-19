# ADR 9: Accumulated retrieval evidence and bounded source readers

Date: 2026-11-20

Status: Implemented locally; requires deployment and live-model evaluation.

## Problem and observed failure

An RL prerequisite question triggered several different searches and accumulated
23 references. The final answer discussed only a few introductory concepts and
described seeing only part of the results. Finding many passages and generating
a long reasoning trace did not establish that the answer model received or used
the distinct evidence.

Inspection found that prompt packing compacted tool results sequentially and
allocated excerpt length relative to at most the first four entries. Earlier
search results could become omission notices while a later result dominated
the remaining budget. The reference ledger retained every retrieved reference,
even references never cited in the answer. Repeated parent windows also inflate
context without adding the matching child passage's distinct information.

## Research informing the decision

- [Lost in the Middle (TACL 2024)](https://aclanthology.org/2024.tacl-1.9/)
  reports sensitivity to the position of relevant evidence in long contexts.
  Larger windows alone do not establish reliable use of all supplied material.
- [Self-RAG (ICLR 2024)](https://arxiv.org/abs/2310.11511) studies adaptive
  retrieval and reflection instead of indiscriminately appending a fixed number
  of passages. Its trained reflection-token model is not implemented here.
- [Corrective RAG](https://arxiv.org/abs/2401.15884) uses retrieval evaluation
  and corrective actions. We adopt the principle of assessing new evidence and
  unresolved aspects, not its trained evaluator or automatic web fallback.
- [Anthropic's context engineering report](https://www.anthropic.com/research/effective-context-engineering-for-ai-agents)
  discusses structured notes and careful compaction. It warns that aggressive
  compression can discard details needed later.
- [Anthropic's multi-agent research system](https://www.anthropic.com/research/multi-agent-research-system)
  uses a lead agent with separate worker contexts for parallel research. It also
  reports substantially higher token usage for multi-agent workflows in its own
  workload. Those measurements are not performance estimates for BDC.

## Decision

Retain the existing ReAct/master and the Deep Retrieval/Drafting/Critique flow.
Add a per-turn evidence workspace and bounded reading workers rather than
spawning autonomous agents for every search or imposing a one-search rule.

### Evidence workspace

Original authorized tool responses remain in the turn history. On private
gateway request copies, successful material/concept/web retrieval results are
pooled, de-duplicated by stable chunk identity or passage identity, and ordered
round-robin across ranked search groups. Prior tool-call IDs retain protocol
receipts; the last retrieval reply explicitly carries accumulated evidence
with the original reference numbers. Recall, errors and content-changing tool
results are not pooled into this workspace.

Excerpt allocation spreads available space across distinct passages before
spending it on long prefixes of the first few passages. Actual model/key input
packing remains authoritative. Important current-user data and tool protocol
remain protected by the existing packer. Source records are untrusted data,
never permission or instructions.

Each fresh successful retrieval reports new unique source entries and repeated
entries to the agent. These are structural novelty signals, not semantic novelty
or a sufficiency score. Prompts require further searching to resolve a named
missing aspect or contradiction, and require consulting accumulated evidence.
No fixed one- or two-search policy is introduced. Existing turn safety limits
and identical-read caching remain.

### Bounded source-reading workers

For read-only answers, readers activate when six or more retrieved passages
exceed half the live request envelope (with a 1200-token floor), or an individual
small source set itself exceeds the envelope. Authoring keeps its existing
canonical/full-source workflow. Matching child passages are preferred over
repeated large parent windows.

Reader work is split into token-bounded source segments using the existing
gateway and `memory_compress` task. At most two jobs run concurrently, with at
most eight logical batches per turn. Gateway/provider fallback retries remain
separate from that logical-job bound. The workflow needs no new provider, key,
binding, dependency or persistent store. Processed segments are reused within
the turn; excess or failed work is reported as pending/unexamined.

Each worker sees the question and its assigned passages. It proposes literal
quotations, original source refs, aspect labels and batch-local gap questions.
The server rejects unknown refs, altered/invented quotations and invalid output.
Only accepted quotation cards replace passage text on private request copies;
original results remain available. Aspect labels and gap questions are model
judgments, not verified facts. The master reconciles them across batches before
deciding whether more retrieval is needed. Quote matching proves attribution,
not source truth, semantic entailment or complete coverage of a passage.

Deep retrieval reuses the same source readers when consolidation is needed,
and the existing critic is instructed to check required-aspect coverage and
contradictions rather than rewarding length or citation count. The implementation
does not introduce an unbounded worker/master/critic loop.

### Diagnostics and presentation

Owned assistant metadata gains optional `decisionExplanation.retrieval_evidence`
counts, carried by existing thinking/done SSE events. Counts distinguish retrieval
calls, received entries, unique source entries, sources in the latest prepared
context, excerpted sources and valid source refs cited in the answer. Optional
reader counts include batches, complete source segments sent to readers,
accepted/rejected quotations and pending work. No raw notes or source text are
added to shared server logs or analytics events.

The UI shows only cited references, preserving original numbers rather than
renumbering a subset. Full retrieved references remain in owned metadata for
compatibility. Older messages/events without diagnostics continue to render.
Prepared/examined/cited counts never measure comprehension or guarantee answer
correctness. Their purpose is to explain where retrieval context was retained
or omitted.

Course-list prompts acknowledge that lists can be abbreviated. A server-verified
page/course anchor is not invalidated by its absence from the displayed list.
Execution-time course authorization, source checks and human approval remain
unchanged; text in documents, reader notes or history cannot grant access.

## Verification and operational limits

Regression tests cover early/middle/late evidence under 2100/4250/8000-token
packing budgets, duplicate removal, original tool-call protocol, input immutability,
quote/ref validation, reader cost/concurrency bounds, unchanged write results,
live/history diagnostics and stable citation numbering. A runtime fixture places
distinctive facts at source tails and confirms the master receives the reader
cards while original sources remain intact.

Model responses are mocked in these tests. They establish data-flow and safety
properties, not improved pedagogical quality. Before claiming a quality gain,
run held-out course questions at deployed model/key budgets and score required
concept coverage, citation entailment, unsupported claims, unresolved
contradictions, latency and token cost against the prior pipeline. Include
prerequisite questions, cross-turn references, contradictory sources, mixed
languages and multi-document comparisons. Do not optimize for answer length,
source counts or the model's self-reported understanding.

The existing `scripts/eval_golden_qa.py` now records elapsed time, model and
retrieval diagnostics, requires actual citations when grounding is expected,
and supports optional lexical aspect-mention checks. The opt-in
`mentor-rl-prerequisite-coverage` case checks foundations, MDP, reward/return,
policy, value, Bellman, exploration and learning order. Select it with
`--case-id mentor-rl-prerequisite-coverage --course-id <authorized-course-id>`
and the evaluator's existing connection/identity arguments. This case does not
run by default or assume a real course ID. Missing keyword groups catch an
obviously incomplete answer; passing them is not proof of correctness, source
entailment or understanding. No live paid inference was run during this change.

Deploy the AI service/worker image for pooling/readers; deploy frontend for the
diagnostic panel and citation filtering. New SSE/metadata fields are optional,
so old/new versions are compatible. No database migration or reindex is needed.
