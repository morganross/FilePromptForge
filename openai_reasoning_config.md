# OpenAI reasoning-effort configuration — design report

Purpose
- Describe how OpenAI-style providers interpret a "reasoning" or "effort" configuration and the practical ways different models may behave differently.
- Provide concrete mapping recommendations for filepromptforge so `cfg["reasoning"]` can be made configurable and consistent across models.
- Call out risks, testing guidance, and recommended defaults.

Executive summary
- Many provider adapters accept a high-level "reasoning" hint (e.g., "low"/"medium"/"high") but there is no single universal switch on all models that does the same thing.
- In practice an adapter or orchestrator must translate the reasoning level into a small set of concrete API parameters and constraints:
  - max_output_tokens (caps how many tokens the model can produce)
  - tool call / web_search limits (max_results, depth)
  - temperature/top_p (controls creativity/randomness)
  - internal flags or prompts that instruct the model to "use more deliberation" (a soft prompt)
- Different models allocate reasoning and token accounting differently; heavier "reasoning" often increases provider cost and can expand usage tokens (including cached_tokens), so guardrails are necessary.

How providers / models typically use a "reasoning" hint
- Soft prompt: adapters prepend or inject an instruction like "Use higher internal chain-of-thought reasoning" or "Explain your reasoning" — this encourages more verbose internal steps and longer outputs.
- Output budget reservation: higher reasoning often pairs with larger `max_output_tokens` to allow the model to produce more reasoning text.
- Tool & memory inclusion: "high" effort may permit the model to call more tools (e.g., more web_search results) and to include more context from those tools in its reasoning — that increases input + cached tokens.
- Model-internal heuristics: newer/larger models may internally change beam/attention behavior given the same prompt; this is model-specific and opaque to clients.

Model differences (illustrative)
- Small/fast models (e.g., "o3-mini", "o3"):
  - Optimized for short, fast answers.
  - "High" reasoning implemented by the adapter's prompt + slightly increased max_output_tokens.
  - Cheaper but limited in deep chain-of-thought; may need explicit tool usage to ground reasoning.
- Mid/large models (e.g., "gpt-4", "gpt-5-nano", "o4/gpt-5"):
  - More capable with long-form internal reasoning; "high" can result in large output and internal token accounting.
  - Providers may show large "reasoning_tokens" and "cached_tokens" when "high" is requested.
  - Risk: runaway token usage if reasoning + tool results are not limited.
- Models with "tool" integrations:
  - If web_search/tool outputs are included back into the model prompt, cached token counts can balloon.
  - Some adapters return heavy sidecars that the model may include in follow-up queries unless managed.

Concrete mapping recommendation for filepromptforge
- Expose cfg["reasoning"] with an enumerated set: "low", "medium", "high".
- Map as follows (defaults can be tuned):

  - "low"
    - max_output_tokens: 512
    - temperature: 0.0 - 0.3
    - web_search.max_results: 1
    - adapter: add short instruction "Answer concisely. Minimal reasoning."
  - "medium"
    - max_output_tokens: 1500
    - temperature: 0.2 - 0.5
    - web_search.max_results: 3
    - adapter: add instruction "Provide a brief explanation and sources."
  - "high"
    - max_output_tokens: 4000 (or model-appropriate cap)
    - temperature: 0.3 - 0.7
    - web_search.max_results: 5 (or smaller if cost-sensitive)
    - adapter: add instruction "Show detailed reasoning/step-by-step and cite sources."

- Additional adapter safety:
  - Always set an absolute hard cap on `max_output_tokens` in the adapter based on model maximums to prevent allocation beyond model limit.
  - When `web_search` is enabled, do not blindly inline full web documents into the request. Instead include only essential snippets or metadata (title, URL, short snippet).
  - For critical/batch usage, consider enforcing an estimated-token guard (client-side) before sending the payload: estimate_tokens ≈ ceil(len(chars) / 4). Abort or truncate if estimate > threshold (e.g., 20k tokens).

Implementation notes for filepromptforge
- Where to implement:
  - In `filepromptforge/providers/openai/fpf_openai_main.py` (adapter) implement a function map_reasoning(cfg_reasoning, model) -> adapter_payload_overrides.
  - In `filepromptforge/file_handler.py` enforce client-side checks before sending (estimate/abort).
- Example pseudo-logic:
  - reason_cfg = cfg.get("reasoning", "medium")
  - overrides = map_reasoning(reason_cfg, adapter_model)
  - payload.update(overrides)
  - if estimate_tokens(payload) > token_threshold: raise/abort or trim payload
- Provide a config section default in `fpf_config.yaml` with:
  - reasoning: medium
  - reasoning_threshold_tokens: 20000
  - reasoning_map: { low: {...}, medium: {...}, high: {...} } — so teams can tune without editing code.

Testing and verification
- Unit tests:
  - Confirm `map_reasoning("low")` sets expected `max_output_tokens`, `temperature`, and `web_search.max_results`.
  - Simulate a large payload and verify client-side guard triggers.
- Integration tests:
  - Run for each model type available (o3, gpt-5-nano, gpt-4) and assert usage numbers remain within acceptable bounds for the configured reasoning level.
- Monitoring:
  - Record `usage` fields in per-run consolidated logs (already implemented). Add alerts if input_tokens or output_tokens exceed configured thresholds.

Security & privacy
- The consolidated per-run log stores the full request payload (including prompt content). If prompts include sensitive info, consider:
  - Redacting sensitive fields before writing the log,
  - Or storing a hashed/sanitized copy instead (configurable).
- Reasoning-level "high" may record long chain-of-thought text in logs; ensure logs are access-controlled.

Sample config snippet (fpf_config.yaml)
```yaml
reasoning: medium
reasoning_threshold_tokens: 20000
reasoning_map:
  low:
    max_output_tokens: 512
    temperature: 0.2
    web_search_max_results: 1
  medium:
    max_output_tokens: 1500
    temperature: 0.35
    web_search_max_results: 3
  high:
    max_output_tokens: 4000
    temperature: 0.5
    web_search_max_results: 5
```

Closing recommendations
- Make `reasoning` configurable and map it to concrete adapter parameters — do not expect the provider to accept a single "reasoning" flag per model.
- Implement a client-side token estimate & guard to avoid runaway provider costs.
- Start with `medium` as default and tune per-model after a few monitored runs.
- Add logging/metrics so you can iterate on the mapping and thresholds with empirical data.
