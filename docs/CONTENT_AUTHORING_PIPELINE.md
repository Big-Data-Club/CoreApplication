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

Legacy Markdown/Mermaid formatters remain compatible. New own-model MCP tools
use the SAME Studio renderer and export PDF/HTML, Markdown and native video.
Focused endpoints `/mcp/studio`, `/mcp/flashcards`, `/mcp/authoring` expose 4, 3
and 6 tools respectively, with 4,000-character default evidence pages (12,000
maximum). Author a compact outline, then one scene per call; card batches hold
1–20 items. Writes require write-scoped credentials and user confirmation.
No text LLM is called. Narration uses the managed paid TTS gateway.
Studio allows two active jobs per user and six new renders per rolling hour by
default (`STUDIO_MAX_ACTIVE_JOBS_PER_USER`, `STUDIO_MAX_RENDER_JOBS_PER_HOUR`).
Retrying an already-active project returns its current job without consuming a
new slot or starting voice generation again.

## Private artifacts, video retention and shared YouTube

V022 adds AI-owned media manifests, idempotency receipts, encrypted shared-channel
connection storage and resumable upload jobs. All new Studio artifacts live in
the private **unversioned** bucket `STUDIO_TEMPORARY_BUCKET` (default
`<MINIO_BUCKET>-studio-temporary`). Reusing the public LMS bucket, an anonymous
policy or enabled/suspended versioning is rejected. Keep IAM access private;
do not set whole-bucket expiration because source artifacts persist.

`source/` contains persistent HTML/storyboard/PDF/Markdown/QA. `temporary/`
contains MP4, per-scene narration and video ZIP, including its MP4/audio. A
manifest is committed before PUT. Staging bytes have a three-hour abandoned-job
deadline; completed video media share **ready_at + 600 seconds**. Source expiry
becomes NULL after successful upload. Each manifest captures its actual bucket
so a configuration change cannot orphan older objects.

Session downloads check owner/course access, support ranges, stream bounded
chunks and set no-store. MCP mints capability links valid at most ten minutes,
never beyond video expiry. Source links can be minted again; expired video links
cannot be renewed. Redact signed query tokens from access logs. Cleanup runs
independently every 15 seconds and retries failed deletes after one minute.
Access expires immediately; physical deletion is eventual when worker/storage
are reachable. Local render scratch is removed on normal completion/cancellation;
keep `/tmp` pod-ephemeral for hard-killed processes.

Rollout registers old `.mp4`/`.mp3`/`.zip` video checkpoints under public
`studio/<project>/` prefixes for immediate retirement. Old public video links
will stop working; narratives and HTML/JSON remain for re-rendering. Flashcard
speech-library caches have their own retention policy, separate from video TTL.

Uploads target the **shared admin-managed YouTube channel**, never a personal
channel. The frontend's worker-only `/api/internal/studio-youtube` bridge checks
the shared service secret and live OAuth channel. Channel data is encrypted with
`AI_KEY_ENCRYPTION_SECRET` in the AI database, replacing ephemeral frontend
`data/youtube-tokens.json`. Admin reconnects once after rollout; old filesystem
credentials are not silently imported. Admin connection routes require a real
ADMIN session and OAuth state. Tokens never reach MCP or the browser Studio proxy.

The user confirms channel ID/name, title, description, privacy, made-for-kids
and synthetic-media settings. A leased job saves an encrypted Google resumable
session and recovers the SAME upload after interruption. Eight-MiB chunks avoid
loading the MP4 into HTTP memory. Maximum five new uploads/user/rolling day;
Google channel/project quotas apply independently. Uploads never extend media
retention. If too late, download before expiry or render again.

Only a processed video with **actual** unlisted/public visibility can become a
course VIDEO draft. Persist its YouTube link and Studio provenance, never an
expiring MP4 URL. Owner/co-teacher permission and section/course membership are
rechecked. Lost-response retries reconcile `studio_project_id` metadata before
creating another draft. PDFs enter the standard LMS document prefix only when
explicitly attached. Students can keep private projects/cards in accepted enrolled
courses without course publication rights. Personal-channel users download the
MP4 and upload it themselves.

Google documents the handshake and `youtube.upload` scope in
[resumable uploads](https://developers.google.com/youtube/data/guides/using_resumable_upload_protocol)
and [videos.insert](https://developers.google.com/youtube/data/reference/rest/v3/videos/insert).
Checked 2026-10-21: the current insert reference describes a separate video-upload
quota bucket (100 calls/day by default). Check the project's console and returned
privacy/upload status rather than historical quota or unverified-project assumptions.
Unlisted links can be forwarded outside the course.

Rollout: migrate through V022; deploy AI HTTP/worker and frontend together; set
private bucket IAM, shared service/encryption keys, the bridge URL
(`http://frontend:3001/api/internal/studio-youtube` on K3s) and existing YouTube
OAuth variables; enable uploads and reconnect as admin. Do not resume a pre-V022
worker during rollback: it would persist public MP4 again. No real paid upload
or deployment is performed by tests. Agent skills are discoverable through
`bdc://skills/catalog`. Detailed payloads are in `bdc://studio/guide` and
`bdc://flashcards/guide`.

Validation: run `python -m pytest --asyncio-mode=auto`. Real renderer regression
tests are opt-in: `STUDIO_RENDER_SMOKE=1 python -m pytest tests/test_studio_render_integration.py`.
They exercise all visual templates and two MP4 layouts with synthetic test audio,
not a neural voice or real API key.
