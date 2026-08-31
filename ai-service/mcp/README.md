# BDC Hub MCP server

BDC Hub exposes a scoped Streamable HTTP MCP endpoint at
`https://bdc.hpcc.vn/mcp`. Users create a bearer token in **My Account → MCP**
and use their own Claude, Codex, or OpenCode model for reasoning.

## Security model

- Raw API keys are shown once and stored only as SHA-256 hashes.
- Keys are read-only or read/write, expire by default, can be revoked, and are
  rate-limited and audited.
- Empty `MCP_ALLOWED_TOOLS` uses the safe built-in allowlist; it never exposes
  every internal agent tool.
- Course-scoped calls fail closed unless LMS confirms the user owns or co-teaches
  the course. Reserved `_context` arguments cannot be supplied by clients.
- Writes require a write-scoped key and the MCP server instructs clients to ask
  for explicit confirmation immediately before the call.
- Slide, quiz, and blueprint content is authored by the external client model.
  BDC validates, formats, or stores a reviewable draft without calling its LLM.

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
labels. MCP turns it into safe Mermaid; Studio turns it into editable native
PowerPoint shapes. An optional `illustration_prompt` can be sent to an image
generator owned by the external client, so BDC neither pays that provider bill
nor fetches untrusted remote image URLs.

Long Studio inputs are budgeted against the smallest configured fallback model.
When raw sources do not fit, every source is mapped into labelled evidence cards
before the final plan call; the UI reports raw/used/budget token estimates. MCP
clients follow the same workflow locally through `bdc-slide-designer` and
`bdc-report-writer`. `mcp_generate_report` formats sourced report sections into
safe Markdown and Mermaid without spending BDC gateway tokens.

## Tests

```bash
cd ai-service
PYTHONPATH=. pytest -q tests/test_mcp
```

See `docs/operations/MCP_SERVER_ROLLOUT_2026-08-29.md` for the full deployment
trajectory and production verification checklist.
