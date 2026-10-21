# BDC Hub content authoring pipeline

Owner: AI service (planning, projects, media and speech jobs); frontend owns the
teacher editor and authenticated BFF. Source of truth is
[`app/services/studio`](../ai-service/app/services/studio) and
[`speech_service.py`](../ai-service/app/services/speech_service.py).

## Outputs and teaching contract

- Slides: deterministic HTML/CSS/SVG, exported as PDF. Studio no longer generates
  PPTX. Original HTML, storyboard, source snapshots and QA screenshots are bundled.
- Lessons/reports: Markdown; existing Mermaid support remains.
- Video: semantic storyboard → HTML/SVG → per-scene neural narration → measured
  audio durations → browser frames → H.264/yuv420p + AAC MP4, 30 fps, faststart.
  Output includes `video.mp4`, `video.html`, `storyboard.json`, `narration/*.mp3`,
  extracted `source/*.md`, `qa.json` and 20/40/60/80% scene screenshots in a ZIP.
  Source snapshots are extracted course text, not copies of original PDF files.

Documents supply facts, terminology, equations and conceptual references. The
outline first identifies learner goals, misconceptions and concept dependencies;
it does not map source pages to scenes or reuse source screenshots/layouts.
One scene teaches one idea with one major diagram and at most three short points.
The teacher reviews the plan and publishes through existing LMS permissions.
`source_refs` preserve `S1..Sn` provenance; references alone do not prove that
all model claims are true. Teacher factual review remains necessary.

The scene compiler owns positions. Supported types include matrix dot products,
tiling, trees, queues, topology, process grids, hierarchy, timelines, comparison,
code and architecture. `visual_spec` contains node IDs, labels/roles, explicit
edges, equations and bounded code; arbitrary generated HTML is never executed.
Matrix templates use symbolic examples unless grounded matrix values are supplied.
Resource bars are schematic ordering, not measured performance. Generated code
snippets are not automatically compiled or benchmarked; no execution claim is made.

Themes use Google/Apple/Microsoft/NVIDIA-inspired palettes and typography, without
company logos. Video defaults to the engineering light palette. `16:9` supports
1920×1080 or `resolution: "720p"` (1280×720). `9:16` is a native 1080×1920 layout,
with 60px left, 150px right and 90px bottom padding; it is never cropped from a
landscape frame. Captions occupy a permanently separate grid region.

## Bounded Groq requests

1. Store up to 100 sources and 2,000,000 total characters with stable labels.
2. Estimate the complete multilingual request, including instructions and JSON.
   Subtract the requested output allowance and a guard before selecting evidence.
3. If sources exceed the smallest configured model/key envelope, split every
   source at text boundaries and map it into evidence cards with names, formulas,
   qualifications and verified source excerpts. Map concurrency is one. A failed
   map preserves an extract and reports the limitation.
4. Produce a compact narrative/outline with a bounded completion.
5. Expand exactly one scene per call, with only its referenced evidence, the
   teaching narrative and concept order. Concurrency is one. Detailed slide/video
   generation failures stop the plan; they cannot silently become empty scenes.
6. The gateway checks the actual leased key/model budget immediately before
   dispatch. It repacks evidence and retries once with a smaller envelope on an
   upstream size rejection. It does not rotate keys to fix oversized prompts.
7. Existing key rotation, fallback, daily token accounting and 429 cooldown remain.
   Explicit upstream Retry-After values are no longer capped at five minutes.
   After key rotation is exhausted, worker authoring can wait/retry twice for
   short 429 cooldowns (at most 120 seconds each); daily exhaustion fails visibly.

`gpt-oss-120b` on Groq has a 131,072-token context window; account TPM/TPD/ITPM/OTPM
can be much smaller. The default unknown-key Groq request envelope is 6,000 tokens.
Configure actual key limits and optionally model `request_token_budget`. GPT-OSS
uses `reasoning_effort: "low"` by default through the pinned SDK's `extra_body`;
model config can override it to `medium`/`high`. Output allowance includes reasoning.
Keys under the same Groq organization share organization quotas; rotating them
cannot increase that quota. See [Groq rate limits](https://console.groq.com/docs/rate-limits).

## Durable execution and timing

Apply forward migrations V020 and V021 before updating AI HTTP and AI worker.
The existing `app.worker.kafka_worker` workload also polls AI-owned `studio_jobs`
and `speech_jobs`; no new Kafka topic or cross-service database access is added.
Both queues use leases, heartbeats and bounded recovery attempts. API restart or
browser navigation does not discard work. One Studio job and one speech job run
per worker replica; scale replicas for capacity. The Studio URL preserves the
project ID for returning to a job. Active jobs lock edits. Missing worker capacity
leaves a visible planning/generating state rather than executing expensive work
inside HTTP. Enqueue errors return failure; there is no in-process fallback.

Studio checkpoints retain completed scene details and narration across worker
recovery; failed-job retries reuse checkpoints only when the input hash matches.
At most three automatic attempts run. Audio checkpoint identity includes narration,
language, the managed voice configuration and an optional `speech_revision` project
setting. Each render job has an immutable artifact prefix, so generating another
version does not overwrite an already published PDF/MP4.

Scene duration is never taken from `duration_est_sec`. Narration is normalized to
MP3, decoded to 48kHz mono PCM, then measured with ffprobe. This excludes MP3
encoder padding from timing. Animation uses normalized local scene time; video
frames use the global measured audio timeline, rounding only frame samples rather
than independently rounding every scene. PCM scenes concatenate before a single
AAC encode, avoiding cumulative AAC priming. Final ffprobe QA checks codecs,
resolution, fps and each stream's duration within 100ms of the measured total.

Browser QA blocks output on text overflow, label intersections or footer/content
collisions. It produces screenshots at four progress points per scene. These DOM
checks do not replace visual/factual review: review the saved screenshots and final
MP4 before publishing. The renderer rejects dense scenes rather than clipping text
or shrinking fonts. A failed QA job includes an actionable error for shortening
text or splitting the scene. Technical diagrams remain vector elements in HTML/PDF;
MP4 frames rasterize the browser output. No raster-image generation is needed.

## Runtime and rollout

The AI Docker image installs pinned Playwright/Chromium, FFmpeg/ffprobe and fonts.
For an existing local Chromium, `STUDIO_CHROMIUM_EXECUTABLE` can override its path;
production normally uses the bundled browser. Worker needs writable temporary disk
for frame encoding and archives. A single video is limited to 30 scenes, 300 seconds
per scene and one hour overall, with a two-hour Studio job timeout. Browser-frame
rendering can take substantially longer than playback; load-test with representative
lectures before enabling concurrent production volume. Video archives currently
assemble in memory for the shared MinIO byte uploader, so size worker memory for
the expected media or restrict lecture length operationally.

Rollout order: migrations → AI image/worker → AI HTTP → frontend submodule. Verify
worker availability and PDF generation first; add a TTS key/voice before video or
neural flashcard smoke tests. These changes do not deploy automatically merely
because local tests pass. Rollback application images while retaining forward
migrations and generated objects; drain active jobs before rolling back to the
old HTTP implementation, which does not understand the `planning` status.

## Shared neural speech

See [LLM gateway operations](llm-gateway-operations.md#neural-speech).
The gateway catalog seeds Runway/ElevenLabs, `eleven_v3` models and a separate
`text_to_speech` binding. It does not create API keys or make paid warm-up calls.
Runway defaults to the Niki preset. ElevenLabs requires the actual account voice ID;
Runway preset names cannot substitute for ElevenLabs voice IDs.

Flashcard speech uses the same managed task, reads card text on the server, checks
owner and course scope, and caches by card/text/language/speed/voice configuration.
Requests return a durable job; audio/status reads are owner scoped through the BFF.
New jobs are limited to 60/hour/owner. Speech failure does not affect card review;
the learner can explicitly select browser speech. No silent voice substitution.
Speech objects remain in MinIO until operational cleanup; deleting a card cascades
job metadata but does not automatically delete its audio object. A retention/cleanup
policy is required before treating these caches as disposable personal data.

## MCP compatibility

Existing MCP tools retain their separate Markdown/Mermaid authoring contract.
This Studio change does not migrate MCP slide export to PDF. Model-authored local
content continues to use the caller's model and does not charge the BDC gateway.

Validation: run `python -m pytest --asyncio-mode=auto`. Real renderer regression
tests are opt-in: `STUDIO_RENDER_SMOKE=1 python -m pytest tests/test_studio_render_integration.py`.
They exercise all visual templates and two MP4 layouts with synthetic test audio,
not a neural voice or real API key.
