# Kafka Event Contracts

| Field     | Value                     |
|-----------|---------------------------|
| Version   | 1.1.0                     |
| Status    | Approved                  |
| Date      | 2026-04-19                |
| Authors   | BDC Team                  |
| Reviewers | —                         |

## Revision History

| Version | Date       | Author   | Description                           |
|---------|------------|----------|---------------------------------------|
| 1.0.0   | 2025-01-01 | BDC Team | Initial contract definition           |
| 1.1.0   | 2026-04-19 | BDC Team | Documentation standardization         |

---

## Overview

The BDC system uses Apache Kafka (KRaft mode) as the event bus between
`lms-service` (Go) and `ai-service` / `ai-worker` (Python).

All messages use JSON encoding (UTF-8). The `value_serializer` in Python is
`lambda v: json.dumps(v).encode('utf-8')`. The Go producer uses
`encoding/json.Marshal`.

Broker address (Docker internal): `kafka:9092`

```
lms-service (Go)                    ai-worker (Python)
      |                                     |
      |--- lms.document.uploaded ---------->|  Document indexing
      |--- lms.ai.command ----------------->|  Async AI jobs
      |--- lms.graph.command -------------->|  Graph maintenance
      |--- lms.maintenance.command -------->|  Reindex tasks
      |                                     |
      |<-- ai.document.processed.status ----|  Index progress
      |<-- ai.job.status -------------------|  AI job progress
      |<-- ai.graph.status -----------------|  Graph job result
```

---

## Topics

### `lms.document.uploaded`

**Direction:** lms-service -> ai-worker
**Purpose:** Trigger document ingestion into the RAG pipeline.
**Consumer group:** `ai-worker-group`
**Retention:** 7 days

#### Schema

```json
{
  "content_id":   1,
  "course_id":    1,
  "file_url":     "courses/1/slide.pdf",
  "content_type": "application/pdf",
  "title":        "",
  "text_content": "",
  "force":        false
}
```

| Field          | Type    | Required | Description                                               |
|----------------|---------|----------|-----------------------------------------------------------|
| `content_id`   | integer | Yes      | Primary key of `section_content` in LMS DB               |
| `course_id`    | integer | Yes      | Course the content belongs to                             |
| `file_url`     | string  | Yes*     | MinIO object key (not a full URL). Required unless TEXT   |
| `content_type` | string  | Yes      | MIME type or `"TEXT"` for Markdown content                |
| `title`        | string  | No       | Display title — used for TEXT content only                |
| `text_content` | string  | No       | Full Markdown body — used when `content_type = "TEXT"`    |
| `force`        | boolean | No       | If true, delete existing chunks before re-indexing        |

**content_type values:**

| Value                | Handler in ai-worker             |
|----------------------|----------------------------------|
| `application/pdf`    | PDFChunker                       |
| `application/vnd.openxmlformats-officedocument.wordprocessingml.document` | DocxChunker |
| `application/vnd.openxmlformats-officedocument.presentationml.presentation` | PptxChunker |
| `video/mp4` (etc.)   | VideoTranscriptChunker           |
| `image/jpeg` (etc.)  | ImageChunker + VLM               |
| `TEXT`               | MarkdownChunker (uses text_content) |
| YouTube URL in file_url | YouTubeTranscriptFetcher      |

---

### `ai.document.processed.status`

**Direction:** ai-worker -> lms-service
**Purpose:** Notify LMS of document indexing progress.
**Consumer group:** Set by lms-service (e.g. `lms-ai-status-group`)
**Retention:** 1 day (status is ephemeral)

#### Schema

```json
{
  "content_id":     1,
  "status":         "indexed",
  "chunks_created": 42,
  "error":          "",
  "job_id":         0
}
```

| Field            | Type    | Description                                      |
|------------------|---------|--------------------------------------------------|
| `content_id`     | integer | Matches the `content_id` from the command        |
| `status`         | string  | One of: `pending`, `processing`, `indexed`, `failed` |
| `chunks_created` | integer | Number of chunks inserted into document_chunks   |
| `error`          | string  | Error message if status is `failed`, else `""`   |
| `job_id`         | integer | Legacy field — always 0, kept for compatibility  |

---

### `lms.ai.command`

**Direction:** lms-service -> ai-worker
**Purpose:** Request an async AI computation (quiz, flashcard, diagnosis).
**Consumer group:** `ai-worker-group`
**Retention:** 7 days

#### Schema

```json
{
  "job_id":       "550e8400-e29b-41d4-a716-446655440000",
  "command_type": "GENERATE_QUIZ",
  "payload":      {},
  "timestamp":    "2025-01-01T00:00:00Z"
}
```

| Field          | Type   | Required | Description                                    |
|----------------|--------|----------|------------------------------------------------|
| `job_id`       | string | Yes      | UUID v4 — used to correlate status updates     |
| `command_type` | string | Yes      | See command types below                        |
| `payload`      | object | Yes      | Command-specific data (see per-command schemas)|
| `timestamp`    | string | No       | ISO 8601 — for debugging/audit only            |

#### Command types and payloads

**`GENERATE_QUIZ`**
```json
{
  "node_id":             42,
  "course_id":           1,
  "created_by":          7,
  "bloom_levels":        ["remember", "understand"],
  "language":            "vi",
  "questions_per_level": 1
}
```
| Field                 | Type         | Required | Default      |
|-----------------------|--------------|----------|--------------|
| `node_id`             | integer      | Yes      | —            |
| `course_id`           | integer      | Yes      | —            |
| `created_by`          | integer      | Yes      | —            |
| `bloom_levels`        | string array | No       | all 6 levels |
| `language`            | string       | No       | `"vi"`       |
| `questions_per_level` | integer      | No       | `1`          |

**`GENERATE_FLASHCARD`**
```json
{
  "student_id": 15,
  "node_id":    42,
  "course_id":  1,
  "count":      5,
  "language":   "vi"
}
```

**`DIAGNOSE_ERROR`**
```json
{
  "student_id":    15,
  "attempt_id":    200,
  "question_id":   88,
  "wrong_answer":  "B",
  "course_id":     1,
  "question_text": "Which pattern uses a mediator?",
  "question_type": "SINGLE_CHOICE",
  "explanation":   "...",
  "correct_answer": "A",
  "answer_options": [
    {"option_text": "A", "is_correct": true},
    {"option_text": "B", "is_correct": false}
  ],
  "node_id": 42
}
```

---

### `ai.job.status`

**Direction:** ai-worker -> lms-service
**Purpose:** Report progress of `lms.ai.command` jobs.
**Consumer group:** Set by lms-service (e.g. `lms-ai-status-group`)
**Retention:** 1 day

#### Schema

```json
{
  "job_id":  "550e8400-e29b-41d4-a716-446655440000",
  "status":  "completed",
  "result":  {},
  "error":   ""
}
```

| Field    | Type   | Description                                               |
|----------|--------|-----------------------------------------------------------|
| `job_id` | string | Matches the `job_id` from the command                     |
| `status` | string | Lifecycle: `pending` -> `processing` -> `completed`/`failed` |
| `result` | object | Command output (see below). Present only when `completed`  |
| `error`  | string | Error message. Present only when `failed`                  |

**Result shapes:**

GENERATE_QUIZ result:
```json
[1, 2, 3, 4, 5, 6]
```
Array of `ai_quiz_generations.id` values (DRAFT status, awaiting review).

GENERATE_FLASHCARD result:
```json
{
  "flashcards": [{"id": 1, "front_text": "...", "back_text": "..."}],
  "count": 5
}
```

DIAGNOSE_ERROR result:
```json
{
  "explanation":        "...",
  "gap_type":           "misconception",
  "knowledge_gap":      "...",
  "study_suggestion":   "...",
  "confidence":         0.85,
  "source_chunk_id":    10,
  "suggested_documents": [],
  "language":           "vi"
}
```

---

### `lms.graph.command`

**Direction:** lms-service -> ai-worker
**Purpose:** Trigger knowledge graph maintenance tasks.
**Consumer group:** `ai-worker-group`

```json
{
  "command": "GLOBAL_LINK"
}
```

Supported commands: `GLOBAL_LINK` (cross-course relationship discovery).

---

### `ai.graph.status`

**Direction:** ai-worker -> lms-service
**Purpose:** Report result of graph maintenance tasks.

```json
{
  "command":      "GLOBAL_LINK",
  "status":       "completed",
  "result_count": 47,
  "error":        ""
}
```

---

### `lms.maintenance.command`

**Direction:** lms-service or admin -> ai-worker
**Purpose:** Trigger background maintenance (reindex, cleanup).
**Consumer group:** `ai-worker-group`

```json
{
  "command":    "REINDEX_CONTENT",
  "content_id": 1,
  "course_id":  1
}
```

Supported commands: `REINDEX_CONTENT`.

---

## Consumer Group Reference

| Group ID              | Service         | Topics subscribed                                                 |
|-----------------------|-----------------|-------------------------------------------------------------------|
| `ai-worker-group`     | ai-worker (Py)  | `lms.document.uploaded`, `lms.ai.command`, `lms.graph.command`, `lms.maintenance.command` |
| `lms-ai-status-group` | lms-service (Go)| `ai.job.status`, `ai.document.processed.status`, `ai.graph.status`|

---

## Error Handling Rules

1. The ai-worker never crashes the consumer loop on a per-message error.
   Every handler is wrapped in `try/except` and publishes a `failed` status.

2. If a command's `job_id` is missing or malformed, the message is logged
   and discarded — no status is published (there is no job to update).

3. LLM rate limit errors (`groq.RateLimitError`) trigger automatic exponential
   backoff (0.5s, 1s, 2s, 4s) before the status is marked `failed`.

4. Document processing failures publish to `ai.document.processed.status`
   with `status: "failed"` and a non-empty `error` field.

---

## Adding a New Command

1. Define the payload shape in this file under `lms.ai.command` -> command types.
2. Add the handler in `ai-service/app/worker/kafka_worker.py` inside `process_ai_command()`.
3. Update `lms-service` Go handler to publish the command and poll `ai.job.status`.
4. Update the result shape documentation under `ai.job.status` -> result shapes.
