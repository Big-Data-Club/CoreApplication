-- Exactly-once application of retryable LMS review deliveries within this DB.
-- Retain receipts for at least the lifetime of replayable LMS quiz effect jobs.
CREATE TABLE IF NOT EXISTS review_delivery_receipts (
 event_id TEXT PRIMARY KEY,
 payload_hash TEXT NOT NULL,
 result JSONB NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
