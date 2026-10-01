# LLM gateway operations

All text and vision calls from `ai-service` route through the LLM gateway. The
gateway stores provider keys encrypted, applies task-to-model bindings, tracks
usage, and manages fallback/cooldown centrally.

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
