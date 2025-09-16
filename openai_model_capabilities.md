# OpenAI Model Capabilities — reasoning & provider-side web_search (Responses API)

Generated: 2025-09-15

## Brief overview
- Purpose: Produce an OpenAI-only mapping that indicates, per model family, whether provider-side web search (Responses API tools: `{"type":"web_search"}`) is supported, whether "reasoning" parameters are supported (and which parameter shapes), and which models support both features together.
- This report consolidates authoritative public sources (OpenAI documentation, Azure docs, OpenAI blog posts, and community posts) gathered during repository work. Where parameter names differ between providers / generations, the report records the most commonly-documented shape and notes incompatibilities encountered (e.g., API rejections when sending unsupported reasoning fields).
- Recommendation: Use a small, per-model capability table in the provider adapter and avoid sending unsupported fields. Prefer a minimal `tools=[{"type":"web_search"}]` tools block by default and map tuning fields (search_context_size, filters) only when the target model/provider accepts them.

## Summary table (OpenAI models)
Notes:
- "Reasoning" field shapes vary. Common documented shapes:
  - `reasoning.effort` / `reasoning_effort`: effort-level enumerations (low|medium|high|minimal) — used by o-series and GPT‑5 reasoning models.
  - `reasoning.max_tokens` / reasoning via `max_completion_tokens` style: some providers or adapters use a token-based reasoning budget.
- "Web search" support is provided via a `web_search` tool in the Responses API. Tool field support (e.g., `filters`, `search_context_size`, `include`) varies per model/provider and may reject unknown fields.
- Where a model is listed as supporting reasoning or web_search, prefer *minimal* shapes initially (e.g., attach `{"type":"web_search"}` with no extra unknown fields) and then map model-specific tuning.

| Model family (OpenAI) | Reasoning supported? | Reasoning param shape (examples) | Web-search (tools) supported? | Notes / Caveats |
|---|---:|---|---:|---|
| gpt-5, gpt-5-mini, gpt-5-nano | Yes (reasoning models) | `reasoning.effort` / `reasoning_effort` (low|medium|high|minimal); also `verbosity` | Yes (Responses API tools: `{"type":"web_search"}`) | GPT‑5 family documents explicit reasoning controls and tools support; use `reasoning_effort` for GPT‑5. Must ensure `max_completion_tokens` large enough to accommodate reasoning+output. Sources: OpenAI GPT‑5 announcements. |
| o4 / o4-mini | Yes (reasoning models) | `reasoning.effort` (low|medium|high) or provider-specific `reasoning` object | Partial / evolving — tool support documented (Responses API); some providers may have limited tool field support | o4-series documented as reasoning-capable and tool-enabled in Responses API docs/announcements. |
| o3 / o3-mini | Yes (reasoning models) | `reasoning.effort` (low|medium|high) or token-based mapping | Varies; historically support for tools in Responses API; check provider mapping | o3/o3-mini are listed among reasoning models; tool support has varied across provider rollouts. |
| o1 | Yes (reasoning models) | `reasoning.effort` | Likely (Responses API) | Documented in provider docs / Azure pages for reasoning models. |
| gpt-4.1 / gpt-4.1-mini / gpt-4.1-nano | Not generally supported for explicit `reasoning.effort` param | No universal `reasoning.effort` documented; do not send `reasoning.effort` for gpt-4.1 family (API may reject) | Mixed — Responses API exposes tools for some gpt-4.1 variants; tool support and accepted tool fields may vary | Observed API rejection when sending `reasoning.effort` for gpt-4.1 — provider returns "unsupported parameter". Use per-model mapping or whitelist reasoning-capable models. |
| gpt-4o / gpt-4o-mini | Mixed / evolving | gpt-4o-mini appears in web_search examples; reasoning param support not universally documented | Web-search tool examples include gpt-4o-mini/gpt-4o | Use minimal tools block and per-model mapping. |
| Other / older models | Varies | Varies | Varies | Always consult provider docs; use per-model mapping. |

## Key takeaways & recommended policy (practical)
1. Enforce "web_search + reasoning" only for models that are officially reasoning-capable and accept the reasoning parameter shape. Recommended initial whitelist:
   - gpt-5 family (gpt-5, gpt-5-mini)
   - o-series reasoning models (o1, o3, o4, o4-mini) — validate exact availability for your org
2. Do not send `reasoning.effort` to models that do not support it (e.g., gpt-4.1 family). Sending unsupported keys results in HTTP 400 / unknown or unsupported parameter errors.
3. Always attach a minimal tools entry: `tools=[{"type":"web_search"}]` in the Responses API request. Avoid passing unknown tool fields at the top-level tools block (some providers reject `tools[0].max_results` etc.). Map per-model tuning explicitly in the provider adapter only when supported.
4. Implement a model-capability mapping in the provider adapter (filepromptforge/providers/openai/fpf_openai_main.py) that:
   - Validates the configured model against a whitelist and chooses the correct reasoning param shape (`effort` vs `max_tokens`) or raises a clear error.
   - Attaches a minimal `tools` block and only adds extra tool fields when the adapter knows the model/provider accepts them.
5. On response: validate that provider performed web_search (look for `web_search_call` / `tool_calls` / web_search output blocks) and that reasoning content exists (top-level `reasoning` or output items with `reasoning`/explanation). Fail and do not write human-readable output when those conditions are not met.

## Example per-model request shapes (recommended)
- GPT‑5 (reasoning-capable)
```json
{
  "model": "gpt-5",
  "input": [{"role":"user","content":"..."}],
  "tools": [{"type":"web_search"}],
  "tool_choice": "auto",
  "reasoning": {"effort": "high"},
  "include": ["web_search_call.action.sources"]
}
```

- o4 / o3 reasoning models
```json
{
  "model": "o4-mini",
  "input": [{"role":"user","content":"..."}],
  "tools": [{"type":"web_search"}],
  "tool_choice": "auto",
  "reasoning": {"effort": "high"}
}
```

- gpt-4.1 (non-reasoning param)
  - Do NOT send a `reasoning` object with `effort` (API may reject). Instead either:
    - Use a reasoning-capable model, or
    - Attach minimal `tools` block and validate reasoning presence in response (weaker enforcement).

## Sources (authoritative / representative)
- OpenAI — GPT‑5 announcement / API docs (overview of GPT‑5 features and reasoning params)
  - https://openai.com/index/introducing-gpt-5-for-developers/
- OpenAI — o3 / o4-mini announcement and Responses API notes
  - https://openai.com/index/introducing-o3-and-o4-mini/
- Azure / Microsoft Learn — Azure OpenAI reasoning models (notes on reasoning_effort and model support)
  - https://learn.microsoft.com/en-us/azure/ai-foundry/openai/how-to/reasoning
- OpenAI community / forum posts describing parameter incompatibilities and web_search examples (representative)
  - (community posts and examples summarized from searches and community threads)
- OpenAI Responses API docs — tools/web_search guidance and examples (web_search tool examples and include fields)
  - (Responses API docs and web_search guide summaries)

Notes on sources
- OpenAI rapidly evolves model capabilities and parameter names; always confirm the exact parameter names and supported fields for your org/tenant in the official documentation and your account's API spec.
- When in doubt, prefer conservative requests: minimal `tools` array + per-model capability checks. Do not send unknown reasoning or tool parameters to models that reject them.

## Next steps I can take (Act mode)
- Run live web searches to expand this mapping with precise doc links per model and create `filepromptforge/openai_model_capabilities.md` (full table with URLs).
- Implement a concrete per-model mapping table inside `filepromptforge/providers/openai/fpf_openai_main.py` (only after you review the mapping).
- Add CI lint that flags unsupported `web_search.enable: false` uses and ensures provider adapter mapping covers configured models.

If you want me to produce the full, source-backed markdown in the repo now, toggle to Act mode and I will run the web searches and write `filepromptforge/openai_model_capabilities.md`.
