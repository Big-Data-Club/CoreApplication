# MCP server rollout — 2026-08-29

This document records the implementation and production rollout path for the
BDC Hub MCP server. It is intentionally operational: a normal push to `main`
must be sufficient; no manual server configuration is required.

## Goal and trust boundary

External clients such as Claude Code, Codex, and OpenCode use the user's chosen
model and provider account for reasoning. BDC Hub exposes only bounded LMS data
and actions. The server does not accept model-provider keys and the deterministic
quiz, slide, and course-blueprint tools do not call the internal LLM gateway.

The browser never calls credential-management endpoints with a caller-selected
identity. My Account calls a same-origin Next.js BFF; the BFF derives `user_id`
from NextAuth and authenticates to AI service with the existing service secret.

## Changes, in order

1. Added the `/mcp` JSON-RPC endpoint with initialize, tools, resources, health,
   request-size and batch-size limits, execution timeouts, metrics, and a coarse
   Traefik rate limit.
2. Replaced plaintext API-key storage with one-way SHA-256 hashes. Raw keys are
   shown once. Keys have read/write scopes, a 90-day UI default, revocation,
   last-used timestamps, a five-active-key limit, and an audit table.
3. Restricted My Account key management to the authenticated frontend BFF,
   validated same-origin writes, and prevented the BFF from proxying arbitrary
   MCP methods.
4. Changed the empty tool configuration from “allow everything” to a built-in
   safe allowlist. Caller arguments beginning with `_` are rejected so internal
   identity and course context cannot be overwritten.
5. Added a fail-closed LMS ownership check before every course-scoped MCP call.
   The `list_knowledge_nodes` cross-course fallback was removed. Course resources
   use the correct LMS routes and `X-API-Secret` header.
6. Reworked slide and quiz tools to validate content authored by the external
   client model. Course creation stores an externally authored, bounded blueprint
   as `DRAFT`; it never accepts raw object-storage keys or auto-publishes.
7. Added a light/dark My Account UI for creating read-only or write-enabled keys,
   one-time secret display, expiry/scope visibility, revocation, and current
   setup snippets for Claude Code, Codex, and OpenCode.
8. Initialized `Big-Data-Club/BDCHub--MCP_SkillSet`, published the first commit,
   and linked it at `ai-service/mcp_skillset`. The skills are also readable as
   MCP resources. Their community license is CC BY-NC-SA 4.0 with separate paid
   commercial licensing; this is source-available dual licensing, not OSI open source.
9. Updated CI checkout to fetch submodules recursively. AI changes build an
   immutable image, apply the idempotent MCP schema before rollout, apply the
   ConfigMap and Ingress, set the image by commit SHA, and wait for rollout.
10. Added a shared visual language for slide decks. Studio produces editable
    PowerPoint infographics on every content slide and Mermaid in Markdown;
    MCP produces a sanitized Mermaid diagram for every slide and optionally
    returns an illustration prompt for the caller's own image-generation tool.

## Push-only deployment path

```text
push main
  → detect ai-service/frontend/config/ingress changes
  → checkout CoreApplication + SkillSet submodule
  → build and push immutable images
  → connect through the runner-owned readable KUBECONFIG
  → apply additive MCP schema
  → apply ConfigMap and Ingress
  → update selected Deployment images
  → wait for rollout and prune stale failed pods/images
```

ConfigMap changes alone do not mutate environment variables inside an existing
pod. The deployment workflow selects the affected service and rolls it, so the
new pod reads the new ConfigMap. Secrets remain in `bdc-secrets`; neither API
keys nor shared secrets are committed to Git.

## Verification

Run locally:

```bash
cd ai-service
PYTHONPATH=. pytest -q tests/test_mcp
cd ../frontend
./node_modules/.bin/eslint \
  src/components/user/manage/McpApiKeyTab.tsx \
  'src/app/api/ai/mcp/[...path]/route.ts'
```

After deployment, create a read-only key in **My Account → MCP**, connect a
client, run `list_my_courses`, and confirm a write tool is denied. Then create a
write key, preview an operation on an owned course, approve it, and verify the
audit entry and LMS result.
