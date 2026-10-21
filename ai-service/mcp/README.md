# BDC Hub MCP server

BDC Hub exposes a scoped Streamable HTTP MCP endpoint at
`https://bdc.hpcc.vn/mcp`. Users create a bearer token in **My Account → MCP**
and use their own Claude, Codex, or OpenCode model for reasoning.

Accepted notifications (including `notifications/initialized` and batches
containing only notifications) return HTTP `202 Accepted` with an empty body,
as required by the [Streamable HTTP transport specification](https://modelcontextprotocol.io/specification/2025-03-26/basic/transports#sending-messages-to-the-server).
Requests with an ID return a JSON-RPC response; mixed batches omit notification
responses.

## Security model

- Raw API keys are shown once and stored only as SHA-256 hashes.
- Keys are read-only or read/write, expire by default, can be revoked, and are
  rate-limited and audited.
- Empty `MCP_ALLOWED_TOOLS` uses the safe built-in allowlist; it never exposes
  every internal agent tool.
- Course reads and private Studio/flashcard writes require LMS-confirmed owner,
  co-teacher or accepted enrollment access. Course lesson writes and shared-channel
  uploads require owner/co-teacher access. Reserved `_context` arguments are server-only.
- Writes require a write-scoped key and the MCP server instructs clients to ask
  for explicit confirmation immediately before the call.
- Slide, quiz, and blueprint content is authored by the external client model.
  BDC validates and persists only the explicitly approved result without calling
  its LLM. The quiz tool can retain Question Bank drafts or assemble complete
  scheduled quizzes with attempt limits; publication remains explicit.

## Client configuration

Claude Code:

```bash
claude mcp add --transport http bdc-hub https://bdc.hpcc.vn/mcp \
  --header "Authorization: Bearer bdc_mcp_REPLACE_ME"
```

Codex (`~/.codex/config.toml`):

```toml
[mcp_servers.bdc_hub]
url = "https://bdc.hpcc.vn/mcp"
bearer_token_env_var = "BDC_MCP_TOKEN"
default_tools_approval_mode = "writes"
```

OpenCode (`opencode.json`):

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "bdc-hub": {
      "type": "remote",
      "url": "https://bdc.hpcc.vn/mcp",
      "enabled": true,
      "headers": { "Authorization": "Bearer bdc_mcp_REPLACE_ME" }
    }
  }
}
```

## Resources and tools

Clients can list authorized course resources and the skills catalog from the
`BDCHub--MCP_SkillSet` submodule. The production allowlist is defined in
`k3s/base/configmap.yaml`. Deterministic authoring helpers clearly state that
their input must first be authored by the caller's external model.

For every readable course, MCP also exposes `bdc://courses/{course_id}/contents`.
It lists sections and individual material URIs. Reading
`bdc://courses/{course_id}/contents/{content_id}` returns the Markdown for a
TEXT lesson or the normalized text extracted when a DOCUMENT was indexed. This
is intended for analysis without exposing the storage object path or downloading
arbitrary binary files. Long documents are paged with `offset_chars` and
`limit_chars` (default 80,000 characters; maximum 200,000). If a document has
not been indexed, the resource reports that no extracted text is available.
Teachers/owners/co-teachers and learners with an accepted enrollment receive
the same read-only material access; all other requests fail closed.

`list_accessible_courses` is the read entrypoint for both teachers and learners:
it returns owned/co-taught courses and accepted enrollments. Knowledge-node and
material search accept either access type, while course mutations still require
owner/co-teacher access and a write-scoped key.

For local knowledge, the MCP client reads only user-selected local files and can
combine them with read-only LMS search. The remote server never receives a local
path or file automatically. A teacher may explicitly approve sending derived
Markdown to `mcp_create_lesson`; the source file remains local. Note that a cloud
model provider can still receive selected excerpts, so truly device-only work
requires a local model and parser.

Slide payloads use the same structured visual language as Content Studio:
`flow`, `cycle`, `comparison`, `hierarchy`, or `timeline`, with 2–6 short
labels. The legacy formatter produces safe Mermaid; Studio renders vector HTML/SVG
and exports **PDF** (no PPTX). An optional `illustration_prompt` can be sent to an image
generator owned by the external client, so BDC neither pays that provider bill
nor fetches untrusted remote image URLs.

Long Studio inputs are budgeted against the smallest configured fallback model.
When raw sources do not fit, every source is mapped into labelled evidence cards
before the final plan call; the UI reports raw/used/budget token estimates. MCP
clients follow the same workflow locally through `bdc-slide-designer` and
`bdc-report-writer`. `mcp_generate_report` formats sourced report sections into
safe Markdown and Mermaid without spending BDC gateway tokens.

## Studio and flashcards with the user's model

Use a focused MCP URL to reduce tool-schema context for small models:

| Endpoint | Exposed tools |
|---|---|
| `/mcp/studio` | Course discovery + `mcp_studio_read`, `mcp_studio_write` (4 total) |
| `/mcp/flashcards` | Course discovery + `mcp_flashcards_read`, `mcp_flashcards_write` (3 total) |
| `/mcp/authoring` | Both workflows + course discovery (6 total) |
| `/mcp` | Existing full allowlisted LMS tool catalog |

Authentication/scopes are identical on all endpoints. Focused profiles default
source reads to 4,000 characters and reject pages over 12,000. Send one scene
or 1–20 flashcards per request; write payload data is bounded at 48,000 chars.
The server exposes `bdc://studio/guide`, `bdc://studio/schema` and
`bdc://flashcards/guide`, plus skills `bdc-studio-producer` and
`bdc-flashcard-author`. Start with those resources instead of guessing payloads.

Studio: create private course project → add authorized source excerpts → compact
narrative outline → one semantic scene per call → render → poll → download or
explicitly upload to the **shared BDC YouTube channel** → attach a course draft.
Slides are PDF/HTML, lessons Markdown, video MP4 with native 16:9 or 9:16 layout.
These authoring tools never invoke BDC's text LLM. Rendering uses the managed
`text_to_speech` gateway and can incur voice-provider charges.

Flashcards: create deck → append reviewed batches with idempotent request UUIDs →
list due cards → review with revision/review UUID → optionally request neural
speech. Semantic verdicts come from the client model; exact matching and review
scheduling happen on the server. Cards remain personal and course scoped.

Studio artifacts use a separate private unversioned MinIO bucket. MP4, per-scene
audio and video ZIP expire 600 seconds after ready; signed downloads cannot
extend that deadline. Cleanup runs every 15 seconds with retries; access expires
even while storage/worker is unavailable. HTML, storyboard, PDF and Markdown remain
owner-scoped. Media URLs never pass through the public LMS `/files` proxy.

Read YouTube channel metadata before upload and confirm the exact channel/title/
privacy/audience/synthetic-media settings. Uploads are durable leased resumable
jobs, limited to five new uploads per user per rolling day, and never extend media
retention. Only a processed video with actual unlisted/public visibility can be
attached as a VIDEO lesson. This creates a draft; publish it through the course
editor after review. A personal channel requires downloading and uploading manually.

See [the authoring operations guide](../../docs/CONTENT_AUTHORING_PIPELINE.md)
for rollout, retention and the shared-channel connection setup.

For complete assessment authoring, `mcp_batch_generate_quiz` accepts
`quiz_settings` with the target section, duration, attempt limit, passing score,
timezone-aware availability window, shuffle behavior, and explicit publication
state. Its standard ladder requires exactly ten explained questions (1–4
remember, 5–7 understand/apply, 8–10 analyze/calculate); advanced questions
retain lesson `source_refs` for review. A write-scoped key and course ownership
are required.

## Tests

```bash
cd ai-service
PYTHONPATH=. pytest -q tests/test_mcp
```

See `docs/operations/MCP_SERVER_ROLLOUT_2026-08-29.md` for the full deployment
trajectory and production verification checklist.
