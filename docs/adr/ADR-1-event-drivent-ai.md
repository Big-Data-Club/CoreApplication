# ADR-001: Event-Driven Architecture for AI Workloads

| Field    | Value                          |
|----------|--------------------------------|
| Status   | Accepted                       |
| Date     | 2025-01-01                     |
| Authors  | BDC Team                       |

## Revision History

| Version | Date       | Author   | Description   |
|---------|------------|----------|---------------|
| 1.0.0   | 2025-01-01 | BDC Team | Initial draft |

---

## Context

The BDC LMS needs to support AI-powered features including:
- Document ingestion into a RAG pipeline (PDF, video, slides)
- Quiz generation using Bloom's Taxonomy
- Error diagnosis with LLM
- Flashcard generation

These operations take between 5 seconds (simple diagnosis) and 5 minutes
(full PDF ingestion with node extraction). HTTP has a default timeout of 30–60
seconds. Running AI workloads synchronously in the HTTP request cycle would
cause the majority of these operations to time out, leaving the user with an
error and no result.

Additionally, the LMS backend (`lms-service`) is written in Go, while the AI
service (`ai-service`) is written in Python. Direct HTTP calls between them
for long-running tasks create tight coupling and require the caller to block
a goroutine for the duration.

## Decision

All AI workloads that take longer than approximately 2 seconds are executed
asynchronously via Apache Kafka.

The pattern is:
1. The caller (`lms-service`) publishes a command event and immediately returns
   `202 Accepted` with a `job_id` to the client.
2. The worker (`ai-worker`) consumes the event, executes the workload, and
   publishes a status event.
3. The caller consumes status events and stores them in Redis.
4. The client polls a status endpoint that reads from Redis.

## Rationale

Kafka was selected over the following alternatives:

### Alternative A: Synchronous HTTP with increased timeouts
- Pros: Simpler architecture, no additional infrastructure
- Cons: Still fails for operations >5 minutes; goroutine blocked during entire operation; no retry semantics; no visibility into in-progress operations
- Reason rejected: Does not solve the fundamental timeout problem

### Alternative B: HTTP with client-side polling of AI service directly
- Pros: No Kafka required
- Cons: Exposes AI service port to LMS service for status queries; creates bidirectional dependency; status stored in Python memory (not durable across restarts)
- Reason rejected: Creates tight coupling; status not durable

### Alternative C: Redis Queue (RQ / Celery)
- Pros: Simpler to operate than Kafka; well-known Python ecosystem
- Cons: Redis is already used for application cache; mixing job queue and cache on the same Redis instance creates operational risk; Celery workers are harder to scale horizontally than Kafka consumers; no built-in message replay for debugging
- Reason rejected: Initially used (Celery), but migrated to Kafka for durability and the ability to replay failed events

### Chosen: Apache Kafka (KRaft mode)
- Kafka is already required in the infrastructure for other purposes
- Messages are durable: failed events can be replayed from offset
- Consumer groups allow horizontal scaling of ai-worker replicas
- Topic separation provides clear audit trail per operation type
- KRaft mode eliminates the ZooKeeper dependency

## Consequences

### Positive
- HTTP requests return immediately; no timeouts regardless of AI workload duration
- ai-worker can scale independently of ai-service
- Failed jobs can be replayed by resetting consumer offset
- Clear separation of concerns: lms-service handles orchestration; ai-worker handles computation

### Negative
- Additional infrastructure dependency (Kafka broker)
- Eventual consistency: clients must poll for results
- Debugging requires correlating events across two topics using `job_id`
- Consumer group offset management must be considered during deployments

### Risks
- Risk: Kafka broker downtime causes all AI features to be unavailable.
  Mitigation: `lms-service` returns a user-facing error message when the Kafka publish fails; the document processing endpoint (`POST /auto-index`) can degrade gracefully.

## References
- `ai-service/app/worker/kafka_worker.py` - consumer loop implementation
- `ai-service/app/worker/kafka_producer.py` - producer functions
- `docs/kafka-events.md` - full event schema reference
