# BDC Hub content authoring pipeline

## Goal

Content Studio and MCP clients should create grounded slides, learning documents
and reports without relying on one oversized LLM request. Image generation is
optional: every artifact remains useful when no image provider is configured.

## Studio flow (BDC gateway)

1. Context sources are stored with stable labels `S1..Sn`.
2. A conservative token estimate uses 2.4 characters/token for multilingual
   text and the smallest context window in the configured fallback chain.
3. If the raw pack fits, Studio preserves it verbatim. If it does not fit,
   every source is split at paragraph boundaries and mapped to evidence cards.
   Calls are concurrency-bounded; a failed map call falls back to a source
   extract instead of failing the entire project.
4. The outline call produces ordered sections and source references using a
   bounded completion.
5. Sections are expanded in batches of at most three. Each batch receives only
   referenced evidence when references are available. A failed batch preserves
   the usable outline and emits a warning.
6. Unknown source references are removed before persistence. The Studio UI
   reports raw tokens, used tokens, budget, and whether hierarchical reduction
   was used.

This avoids silent tail truncation and bounds both input and output. It costs
additional gateway calls only when reduction/detail batches are necessary.

## Visual contract

Each authored section has:

- `visual_type`: auto, flow, cycle, comparison, hierarchy or timeline;
- `visual_labels`: two to six concise labels;
- `alt_text`: accessible description;
- `illustration_prompt`: optional suggestion for a future/user-owned image generator;
- `source_refs`: grounding labels.

PPTX uses editable native shapes. Markdown/report output uses sanitized Mermaid.
An illustration prompt is rendered as a clearly labelled suggestion and is not
treated as an existing image. Image-provider failure must never fail authoring.

## MCP flow (user-owned model)

MCP does not charge the BDC gateway for authoring. `bdc-slide-designer` and
`bdc-report-writer` instruct Claude, Codex, OpenCode or a local model to build
evidence cards and author in bounded batches. `mcp_generate_slide_deck` and
`mcp_generate_report` then validate and format the supplied structure into safe
Markdown/Mermaid. Local paths and original local-only files are never included;
citations use neutral aliases and page/heading references.

## Operational limits

- Studio sources: maximum 8 sources, 6,000 stored characters per source.
- Studio section detail: batches of at most 3, two concurrent batches.
- Evidence reduction: up to 3 concurrent calls.
- MCP slides/reports: maximum 30 sections.
- Optional image prompts: maximum 1,000 characters.

Administrators should bind `content_studio` to at least one structured-output
model with an 8K or larger context window. Larger windows reduce map calls but
are not required for correctness.
