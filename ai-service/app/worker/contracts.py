"""Stable lane identifiers shared by producers, consumers and diagnostics."""

BATCH_TOPIC = "lms.ai.command"
BATCH_GROUP = "ai-worker-group"
INTERACTIVE_TOPIC = "lms.ai.interactive"
INTERACTIVE_GROUP = "ai-worker-interactive"
MEMORY_TOPIC = "lms.ai.memory.v1"
MEMORY_GROUP = "ai-worker-memory-v1"
DEAD_LETTER_TOPIC = "ai.worker.failed.v1"
