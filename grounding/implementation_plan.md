Implementation plan — Add Provider-API Web Search (Grounding) to FilePromptForge (FPF)
====================================================================================

Purpose
-------
Provide a focused, actionable design and implementation plan to add provider-side web‑search grounding to FilePromptForge (FPF) under the following constraints:
- No MCP, no client-side/local search, and no external-search fallbacks.
- Grounding must be performed only via provider-side web search features exposed by the provider API.
- Grounding must be explicitly enabled by the user (opt-in) and will only be attempted for models that support provider-side web search tools.

High-level summary
------------------
- Implement a Grounder component that calls only provider-side web-search tool APIs (e.g., OpenAI Responses API tools, OpenRouter plugin/:online, Google Gemini grounding) — no client-side web scraping or third-party search services.
- Require an explicit configuration flag to enable grounding; if grounding is enabled, the Grounder will detect whether the selected model supports provider-side web search and proceed only when supported.
- If the provider or model does not support provider-side web search, the system will report the capability as unavailable and will not attempt any alternative client-side searches.
- Ensure auditing and metadata: record which provider/tool was used and the source references returned by the provider (if provided) in the output.
- Keep grounding opt-in and backward compatible with existing flows when grounding is disabled.

Scope & goals (refined)
-----------------------
- Provider-API only: use only first-party provider features that perform the web search on the provider side (tools, plugins, or model variants that include web access). No local or third-party search services, no MCP tool orchestration implemented locally.
- Capability gating: only call provider web-search when the model is known to support it or the provider confirms support at runtime.
- Explicit enablement: add config/CLI flag to enable grounding; by default it is disabled.
- Clear behavior when unavailable: when grounding is enabled but the provider/model does not support web search, the run should log/report "grounding not available for provider/model" and proceed without grounding (or abort, based on config).
- Preserve privacy and logging: do not leak API keys into logs; record provider-provided citations/source lists if returned.

Design changes (concentrated)
-----------------------------
1. Grounder component (provider-only):
   - Single orchestrator (filepromptforge/grounding/grounder.py) that:
     - Accepts configuration: provider, model, grounding_enabled (bool), grounding_approve (bool), grounding_options (max_results, search_prompt).
     - Performs capability detection (see below).
     - Builds provider-specific requests that enable provider-side web search tools.
     - Parses provider responses and extracts the final text and any returned sources/tool outputs.
     - Returns structured result: { response_text, sources: [...], method: "provider-tool", provider: "openai"|..., tool_details: {...} }.

2. Provider adapters (provider-only, no external search):
   - openai_adapter.py
     - Implements calls to the OpenAI Responses API with tools=[{"type":"web_search_preview", ...}] or uses chat/search-preview model ids where appropriate (e.g., gpt-4o-mini-search-preview) and passes web_search_options if the chat endpoint supports it.
     - Capability detection: check model id against a maintained whitelist (seeded from api_web_search_capability_chart.md) and/or attempt a lightweight capability probe (see detection strategy below).
     - Parse provider response: handle response.output_text, tool_call objects and any citation fields the provider returns.
   - openrouter_adapter.py
     - Use OpenRouter's provider-side mechanisms that run web search on the provider (plugins with id "web" or the `:online` suffix) — these are provider-side features, so they are allowed.
     - Capability detection via model metadata from OpenRouter catalog (if available).
     - Parse returned sources/citation fields, if any.
   - google_adapter.py (Gemini)
     - Map grounding settings to Gemini's grounding flags and use only provider-side grounding.
     - Detect support for the selected Gemini model.

3. Config & CLI
   - Add `grounding` block to Config (gpt_processor_main.py):
     grounding:
       enabled: false
       provider: openai              # openai | openrouter | google
       max_results: 5
       search_prompt: "Incorporate and cite these sources:"
       approve_tool_calls: false     # if true, the GUI/CLI must request interactive approval before provider web search
   - CLI flags:
     --grounding (enable)
     --grounding_provider
     --grounding_max_results
     --search_prompt
     --grounding_approve

4. Integration into processing loop
   - Before sending the prompt to the model, check if grounding.enabled is true.
     - If false: call APIClient.send_prompt(...) as current behavior.
     - If true:
       1) Use Grounder.capability_check(provider, model) to confirm provider-side web search is supported by the selected model. If not supported:
          - Behavior depends on config: either log and proceed without grounding, or abort with a clear error (configurable; default = proceed without grounding and log).
       2) If supported, Grounder invokes the provider adapter to perform a single provider-side request that includes the provider web-search flags/tools/plugins.
       3) Grounder receives the provider response, extracts final_text and any provider-supplied source/citation metadata, and returns it to the main flow.
   - Write outputs exactly as normal, but include metadata (method, provider, tool details, sources) in a metadata header or separate JSON file.

Capability detection strategy
-----------------------------
- Maintain a curated whitelist of model ids known to support provider-side web search (seed from filepromptforge/grounding/api_web_search_capability_chart.md).
- At runtime:
  - If model id is in whitelist → consider supported.
  - If not in whitelist and provider exposes a models or metadata API (e.g., OpenRouter catalog), query it to check for web search capability.
  - If ambiguous and the provider supports a safe, lightweight probe API call to check tool availability, use a short probe (very small request) guarded by the `grounding_approve` flag; if probe returns "tool not allowed" or permission error — treat as unsupported and do not attempt provider web search.
- Never fall back to client-side search — if provider tool is unavailable, either continue without grounding or abort (configurable).

Provider-specific implementation notes (API-only focus)
-------------------------------------------------------
OpenAI (Responses API)
- Preferred path: Responses API with `tools=[{"type":"web_search_preview", ...}]` and optional `tool_choice` to force using the web_search tool.
- Chat endpoint alternative: use special search-enabled model ids (e.g., `gpt-4o-mini-search-preview`) and pass `web_search_options` if the model supports it.
- Example (Python, conceptual):
    from openai import OpenAI
    client = OpenAI(api_key=...)
    response = client.responses.create(
        model="gpt-4.1",  # or another web-search-capable model
        tools=[{"type":"web_search_preview", "max_results": grounding_opts.max_results}],
        input="What changed in USB4 v2?"
    )
    text = response.output_text  # or parse response.output for structured tool outputs
- The code must handle cases where the provider returns structured tool outputs; extract both final text and any cited sources.

Important OpenAI caveats
- Tool availability varies by account and model snapshot. Capability detection is critical.
- Responses API may return tool_call objects and structured outputs rather than a single text field; parse both paths.
- Provider-side searches are billed/limited by provider policies — document costs in README.

OpenRouter (provider-side)
- Use `plugins: [{"id":"web", ...}]` or append `:online` to model slugs that support provider-side web search.
- These are provider-side web searches performed by OpenRouter; they are allowed under the "API-only" rule.
- Query the OpenRouter model catalog (if available) for capability detection.

Google Gemini (Grounding)
- Use Gemini's provider-side grounding flags/options when supported (Gemini 2.5+). Implement mapping from grounding options to Gemini request fields.
- Behavior: provider performs the web search and returns augmenting context; parse returned citations if present.

Response parsing & output
-------------------------
- Extract final text and any provider-provided sources/citation structures from the API response.
- Persist these in the output directory alongside the response text:
  - response_<filename> (text)
  - response_<filename>_metadata.json (includes provider, model, method: "provider-tool", tool_details, sources array, timestamp)
- Maintain clear logs describing whether grounding was used and which provider/model/tool produced the result.

User approval & safety
----------------------
- Provide `grounding.approve_tool_calls` flag: when true, require user interaction (in GUI or interactive CLI) before making provider-side web-search calls (useful for security/privacy).
- Default: approve_tool_calls = false (automatic) but grounding remains opt-in via grounding.enabled.
- Redact API keys from logs and avoid printing sensitive tokens.

Errors, retries, and failure modes
---------------------------------
- If the provider returns an explicit "tool not available" or "permission denied" error, Grounder must treat grounding as unsupported for that run (log the condition and continue without grounding or abort based on config).
- For transient provider errors (5xx), implement retries with exponential backoff (configurable).
- Do not attempt client-side search or other fallbacks.

Testing & validation
--------------------
- Unit tests for openai_adapter and openrouter_adapter using mocked provider responses, including:
  - Successful provider-tool response with sources.
  - Provider returning tool-not-available error.
  - Provider returning structured tool_call outputs vs plain text.
- Integration tests (optional) against sandbox accounts for supported models (requires credentials).
- Manual test flow:
  - Enable grounding in config, select a known web-search-capable model, run with a sample input, and verify output metadata contains provider sources.
  - Try with grounding enabled and a non-capable model to verify graceful handling.

Documentation & installer GUI
-----------------------------
- Update README to document that grounding:
  - Is provider-API-only.
  - Must be explicitly enabled.
  - Only works on certain provider models; list examples and point to the capability chart.
  - May require account-level feature enablement by the provider.
- Installer GUI:
  - Add fields to write grounding config (provider, enabled flag, max_results, search_prompt, approve_tool_calls) into default_config.yaml.
  - Do not implement local search or MCP functionality in GUI — explicitly warn users grounding requires provider-side support and may require additional account permissions.

Migration & backward compatibility
---------------------------------
- Default behavior unchanged: grounding disabled.
- If grounding is enabled in config:
  - System attempts provider-side grounding only for supported models.
  - If unsupported, behavior is configurable: proceed without grounding (default) or abort.

Milestones (API-only)
---------------------
1. Add filepromptforge/grounding/grounder.py and provider adapters:
   - filepromptforge/grounding/adapters/openai_adapter.py
   - filepromptforge/grounding/adapters/openrouter_adapter.py
   - filepromptforge/grounding/adapters/google_adapter.py
2. Update gpt_processor_main.py:
   - Extend Config to read grounding block.
   - Add CLI flags for grounding.
   - Integrate Grounder into processing loop.
   - Add output metadata writing.
3. Add unit tests and documentation updates.
4. Add GUI wiring to write grounding fields to default_config.yaml (optional).

Appendix: Notes & pitfalls
--------------------------
- Providers differ in how they expose provider-side web search; always parse provider responses for both text and structured tool outputs.
- Model capability and provider account permissions are the limiting factors — ensure detection and clear user messaging.
- Keep grounding strictly provider-side; do not add any client-side search paths.

End of implementation plan (API-only).
