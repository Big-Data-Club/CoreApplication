# Studio vector media and shared neural speech

Status: implemented; deployment and live voice validation require operator rollout.

Studio previously routed both slides and its video placeholder through PPTX. Large
plans also competed with Groq request/TPM limits. Flashcard reading used only browser
voices. These paths need deterministic educational visuals, measured audio timing
and one managed provider/key boundary.

Use semantic scene data, never LLM-authored pixels or source slide screenshots.
Build a teaching narrative before scene expansion. The renderer owns HTML/CSS/SVG,
native landscape/portrait layouts, captions and overflow checks. Slides export PDF
and source HTML; study documents remain Markdown. Video derives its global timeline
from per-scene PCM durations measured by ffprobe, then encodes H.264/AAC once.

Keep provider/model/task/key management in the existing gateway. Seed a separate
`text_to_speech` task for Runway/ElevenLabs without keys or paid warm-up calls.
Flashcard speech reads AI-owned card text by owner/course, with authenticated
polling and cached audio. Voice configuration remains server-side.

Use AI-owned Postgres queues with fenced leases and checkpoints, consumed by the
existing AI worker workload. HTTP enqueues long work; no new Kafka contract or
service database access is introduced. Each render gets an immutable object
prefix. Teacher edits invalidate artifacts and LMS publication stays explicit.

Reduce large documents into labelled evidence and expand one scene per completion.
Reserve output before dispatch and use bounded worker waits after short quota
failures. Key rotation remains intact; organization-wide Groq quota cannot be
increased by rotating keys within that organization.

Costs include a larger worker image, CPU/disk for browser rendering and temporary
memory for archives. Automated screenshot/DOM/media checks supplement teacher
factual and visual review. Real provider synthesis is unverified until a key and
voice are configured. Operational cache retention needs explicit handling; MinIO
objects are not automatically removed when card metadata is deleted.

Implementation, limits, checks and rollout:
[content authoring pipeline](../CONTENT_AUTHORING_PIPELINE.md),
[gateway operations](../llm-gateway-operations.md#neural-speech).
