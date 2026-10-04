# LLM gateway operations

All text and vision calls from `ai-service` route through the LLM gateway. The
gateway stores provider keys encrypted, applies task-to-model bindings, tracks
usage, and manages fallback/cooldown centrally.

## Optional Jev decision service

Jev System One is a structured decision API. On first startup the gateway
registers the `opencode_zen` provider, the `jev-1.13-free` model, and a
`jev_decision` task binding. This is a catalog default only: runtime resolves
the active task binding, model, provider URL and encrypted key pool from the
gateway. Admin changes are retained across restarts. The application default
is disabled; the production ConfigMap opts in. Without a usable binding/key,
routing uses the existing local rule. To disable after rollout, set
`JEV_ENABLED=false` and restart `ai-service`.

To choose another provider or System One model, create it in Admin > LLM
Configuration. Set the model's JSON config to `{"api_protocol":"system_one"}`;
optionally set `endpoint_path` (default `systemone`). Give its provider an HTTPS
Base URL and an active API key, then add the model to the `jev_decision` task
binding chain with a higher priority or pin it. Only System One models can be
bound to that task. Key and binding changes take effect without a pod restart
(binding caches on other processes can take up to 30 seconds). The gateway
appends the model's endpoint path to its provider's Base URL.

For read-only Deep questions, Jev evaluates up to 900 characters of the current
question and returns an advisory probability for the retrieval/draft/critique
pipeline. A score of at least 0.85 may promote a local score in the 0.35–0.45
band. It cannot approve writes or bypass course authorization. MCP also exposes
the read-only `assess_question` tool for explicit assessment, returning an
unavailable error when Jev is disabled. Operators should review the external
transfer and provider retention terms before enabling the feature in production.
System One models must not be bound to chat tasks.

## Default routing

Text tasks bootstrap to the configured default model. `agent_flash`, used only
by the chat UI's Flash mode, reads `AGENT_FLASH_MODEL` at startup; when it is
empty, it uses `CHAT_MODEL`. This keeps the latency-first path independent from
the tool-capable `agent_react` binding without pinning a provider model in
source. A vision task keeps its separate vision-capable binding; do not bind a
text-only model to it.

For Compose and K3s, set `AI_FLASH_MODEL` in `.env`; the runtime manifests map
it to `AGENT_FLASH_MODEL`. The K3s runtime preparation script now copies that
setting (and `LLM_REQUEST_TOKEN_BUDGET` / `LLM_TPM_SAFETY_RATIO`) into its
override ConfigMap, so the selected gateway model is not lost at deployment.
For a Groq key with an 8K TPM allowance, the shipped request budget is 6K with
a 0.75 safety ratio. Raise those settings only after updating the key's TPM
limit in the gateway configuration.

Change a model, fallback order, TPM/RPM limit, or API key in
`/lms/admin/llm-config`. Admin-created or pinned bindings are not overwritten
by application startup. Set `AI_FLASH_MODEL` in runtime configuration before a
first bootstrap, or bind a faster approved model to `agent_flash` in the admin
UI. Do not repurpose `agent_react`, which serves the standard and deep tool
workflows.

## OpenAI API key

ChatGPT subscriptions and API billing are separate. Enable API billing at the
OpenAI Platform, create an API key, then add it in **Cấu hình LLM → Keys** to
the built-in **OpenAI API** provider. The key is encrypted before it is stored.

`OPENAI_API_KEY` is an optional bootstrap mechanism for deployment. Put a real
key only in the runtime secret manager, never in this repository. The shipped
Kubernetes value is a deliberately ignored placeholder.

## Large-course overview generation

The overview workflow is coverage-preserving map/reduce:

1. Every source chunk is put into a bounded local synopsis batch.
2. Large sets of synopses are progressively reduced to evidence cards.
3. The final Vietnamese/English lesson uses the evidence cards, with source
   references retained.

No source text is silently truncated. The gateway also preflights estimated
input + output tokens, including tool schemas and tool-call metadata, and
respects the configured request budget and a key's TPM limit before calling a
provider.
