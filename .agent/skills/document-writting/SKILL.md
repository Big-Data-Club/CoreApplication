---
name: bdc-docs-writer
description: >
  Use when writing any documentation for the BDC CoreApplication project.
  Covers: API docs, architecture docs, developer guides, technical notes,
  ADRs, onboarding guides, Kafka event contracts. All docs use ASCII diagrams,
  no emoji, formal technical English, and follow the BDC documentation standard.
triggers:
  - documentation
  - docs
  - write docs
  - developer guide
  - technical note
  - architecture doc
  - adr
  - api doc
  - onboarding
  - README
  - kafka events
version: "1.1"
authors:
  - BDC Team
requires:
  - bdc-core-orchestrator
---

# BDC Documentation Writer - Skill

## Non-Negotiable Rules

```
1.  No emoji or decorative icons anywhere in the document.
2.  All diagrams must be ASCII art - no Mermaid, no PlantUML, no image embeds.
3.  Every public API endpoint must document request, response, and error cases.
4.  Every document must have a header block: title, version, date, status, authors.
5.  Technical claims must reference the source file, config key, or migration.
6.  Formal technical English. No contractions. No casual language.
7.  Passive voice is acceptable for process descriptions. Active voice for instructions.
8.  All code blocks must specify the language identifier.
9.  Documents must be self-contained - no undefined terms or unexplained acronyms.
10. Write in the present tense for current state, future tense for planned work.
```

---

## Document Header Block (Required on Every Document)

```markdown
# Document Title

| Field     | Value                     |
|-----------|---------------------------|
| Version   | 1.0.0                     |
| Status    | Draft / Review / Approved |
| Date      | YYYY-MM-DD                |
| Authors   | BDC Team                  |
| Reviewers | -                         |

## Revision History

| Version | Date       | Author   | Description   |
|---------|------------|----------|---------------|
| 1.0.0   | YYYY-MM-DD | BDC Team | Initial draft |
```

---

## Document Types

### 1. Architecture Document

Required sections:
```
1. Overview - purpose, problem solved, scope
2. Architecture Diagram (ASCII)
3. Component Responsibilities - one paragraph per component
4. Data Flow - numbered step-by-step for the primary request path
5. Data Model - key tables with columns and relationships
6. Configuration - all environment variables with type, required flag, default
7. Known Constraints - explicit statements about limitations
8. Open Questions / Future Work
```

**ASCII Diagram Standards:**

```
Component boxes:
+---------------------+
|  Component Name     |
+---------------------+

Data flow arrows:
--->   unidirectional
<-->   bidirectional
- - -> async / fire-and-forget

Label arrows with protocol or description:
          HTTP POST /sync
  [Auth]  --------->  [LMS]
          X-Sync-Secret header

Layer diagrams (stack vertically):
+----------------+
|   Handler      |
+----------------+
        |
        v
+----------------+
|   Service      |
+----------------+
        |
        v
+----------------+
|   Repository   |
+----------------+
```

---

### 2. API Reference Document

Required structure per endpoint:

```markdown
### [METHOD] /api/v1/path/to/endpoint

**Description:** One sentence.
**Authentication:** Bearer JWT / X-Sync-Secret / X-AI-Secret / Public
**Authorization:** Role requirements

#### Request

| Field  | Type    | Required | Constraints | Description |
|--------|---------|----------|-------------|-------------|

```json
{ "example": "body" }
```

#### Response - 200 OK

| Field  | Type    | Always Present | Description |
|--------|---------|----------------|-------------|

```json
{ "example": "response" }
```

#### Error Responses

| Status | Condition                              |
|--------|----------------------------------------|
| 400    | Malformed JSON or validation failure   |
| 401    | Missing or expired JWT                 |
| 403    | Authenticated but insufficient role    |
| 404    | Resource does not exist                |

#### Notes
- Side effects (e.g., triggers async user sync)
- Rate limits
- Idempotency guarantees
```

---

### 3. Architecture Decision Record (ADR)

File location: `docs/adr/ADR-NNN-short-title.md`

```markdown
# ADR-NNN: Short Title

| Field  | Value                                              |
|--------|----------------------------------------------------|
| Status | Proposed / Accepted / Deprecated / Superseded      |
| Date   | YYYY-MM-DD                                         |
| Authors| BDC Team                                           |

## Context
Situation requiring a decision. Forces at play.

## Decision
"We will use X because Y." - one or two sentences.

## Rationale
Why this decision over alternatives. Reference benchmarks or prototypes if consulted.

## Alternatives Considered

### Alternative A: Name
- Pros: ...
- Cons: ...
- Reason rejected: ...

## Consequences

### Positive
- ...

### Negative
- ...

### Risks
- Risk: description - Mitigation: mitigation

## References
- Source file or link
```

---

### 4. Technical Notes Entry

Format: numbered, independent notes. Each stands alone.

```markdown
### TN-NNN: Short Title

**Context:** Why this note exists. What problem it addresses.

**Detail:** Full explanation. Reference the relevant source file or config key.

**Impact:** What breaks if this is ignored.

**Fix / Workaround:**
```bash
# concrete command if applicable
```
```

---

### 5. Kafka Event Contract

Required sections per topic:
```
- Topic name, direction, consumer group, retention
- Schema table (field, type, required, description)
- Example JSON payload
- Per-command payloads (for lms.ai.command)
- Result shapes (for ai.job.status)
```

---

## ASCII Sequence Diagram Template

```
  Client          Auth Service       LMS Service         AI Worker
    |                   |                  |                  |
    |-- POST /login ---->|                  |                  |
    |                   |-- SELECT user --->|                  |
    |<-- 200 + JWT ------|                  |                  |
    |                   |                  |                  |
    |-- GET /courses ---------------------->|                  |
    |                   |                  |-- Kafka PUB ----->|
    |<-- 202 {job_id} --|------------------|                  |
    |                   |                  |         process  |
    |                   |                  |<-- Kafka PUB ----|
    |-- GET /jobs/{id} ------------------>|                  |
    |<-- 200 {status} ---|-----------------|                  |
```

---

## File Naming Convention

```
docs/
  DEVELOPER_GUIDE.md          Setup and contribution workflow
  DEVELOPER_GUIDE.en.md       English version
  TECHNICAL_NOTES.md          Non-obvious gotchas and operational knowledge
  kafka-events.md             Kafka event contracts and schemas
  adr/
    ADR-001-event-driven-ai.md
    ADR-002-qdrant-over-pgvector.md
    ADR-003-neo4j-knowledge-graph.md
  api/
    ai-service-api.md
    lms-service-api.md
    auth-service-api.md
```

---

## Writing Checklist

```
[ ] Header block present with version, status, date, authors
[ ] Revision history table present
[ ] All diagrams are ASCII
[ ] No emoji anywhere
[ ] All env var names match exactly what is in .env.example
[ ] All endpoint paths match the router registration in source code
[ ] All code blocks have a language identifier
[ ] Every error scenario documented
[ ] Formal English - no contractions
[ ] Claims reference a source file or config key
[ ] Document is self-contained
[ ] Spell-checked
[ ] Placed in the correct location
```