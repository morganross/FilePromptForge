Grounding: provider-side API grounding vs client-side websearch — explanation and policy

Purpose
-------
This short README explains the difference between provider-side API grounding (what this project calls "API grounding") and client-side websearch (external-search), states the project's policy, and gives clear guidance for implementers. This file is intended to be the canonical top-level grounding README for the repository.

Definitions — simple and concrete
--------------------------------
- API grounding (provider-side grounding)
  - Description: The language-model provider (OpenAI, Google Gemini, OpenRouter, etc.) performs the web retrieval internally when you enable the provider's grounding/web-search option for a model. The provider receives a single API request which may trigger internal multi-step browsing, and returns the final text along with optional citation/source metadata.
  - Example provider mechanisms:
    - OpenAI Responses API with tools=[{"type":"web_search_preview", ...}]
    - OpenAI/preview search-enabled models (e.g., gpt-4o-mini-search-preview) + web_search_options
    - Google Gemini "Grounding with Google Search" tool
    - OpenRouter plugin "web" or model slug suffix `:online`
  - Properties:
    - The provider executes the web fetches on their servers.
    - Billing, rate limits, and privacy are governed by the provider.
    - The provider can return structured tool_call outputs and citations.
    - No local orchestration (no MCP, no external agent orchestration) is required.

- Client-side websearch (external-search fallback)
  - Description: The client (FPF) calls an external search API or engine (SerpAPI, Bing Web Search API, Google Programmable Search, etc.), collects top results/snippets, and injects that content into the prompt sent to the chosen model.
  - Properties:
    - The client controls the search, fetches, and snippet selection.
    - Works with any model, but increases complexity (snippet selection, context size, sanitization, PII concerns).
    - Different billing and rate limits (search provider + model provider).
    - Requires careful source tracking and sanitization.

Policy for this project (explicit)
----------------------------------
- No use of MCP/agents/tavily or provider-external tool orchestration frameworks.
  - Do not rely on local MCP servers, third-party "agent" frameworks, or Tavily tooling.
- Supported modes (allowed):
  1. Provider-side API grounding (preferred): Enable provider-native web-search/grounding features through the provider's API in a single request (Responses API tools, Gemini grounding, OpenRouter plugin/:online, etc.). This is the primary supported mode.
  2. Client-side websearch (external-search) is allowed only if explicitly enabled in configuration and documented; it must be implemented as a separate, opt-in fallback and not as the default. When used, it must not use MCP/agent toolchains either.
- Forbidden:
  - Any approach that relies on MCP servers, Tavily, or other agent-control tooling.
  - Implicit/hidden background tool use that the user has not explicitly enabled.

Why the distinction matters
--------------------------
- Simplicity: Provider-side grounding keeps the flow simple (one API call) and avoids maintaining a separate search orchestration layer.
- Reliability and attribution: Providers that perform grounding may return structured citations in a consistent format.
- Privacy & compliance: Provider-side grounding keeps web retrieval on provider servers under their policy; client-side search requires careful handling of what is sent to external search providers.
- Feature availability: Not all models or accounts support provider-side grounding. A runtime capability check is required.

Recommended behavior for FilePromptForge (summary)
--------------------------------------------------
- Default: grounding disabled.
- Opt-in: Add a grounding config block (enabled: boolean). When enabled:
  - If using API grounding: attempt provider-side grounding only for models that are known to support it or when provider metadata/probe confirms support.
  - If API grounding is unavailable for the chosen model and the user explicitly allowed external-search fallback in config, then perform client-side websearch as the fallback (only when configured).
  - If API grounding is unavailable and external fallback is NOT allowed, log/report "grounding not available for provider/model" and continue without grounding (or abort, based on an explicit config flag).
- Logging & metadata: Always record method ("provider-tool" or "external-search"), provider, model, and returned sources in a metadata JSON next to the response text.
- Approval: Support an approve_tool_calls flag so users can require manual approval before any provider-side grounding call.

Quick implementation notes
--------------------------
- Capability detection: Maintain a curated whitelist of provider model ids that support provider-side grounding and/or implement a safe probe to confirm support at runtime.
- Parsing: Providers differ — some return structured tool_call outputs, others plain text. Implement a canonical response schema:
  { text: str, sources: [ {title, url, snippet} ], provider: str, model: str, method: "provider-tool" | "external-search", tool_details: {} }
- Security: Never log API keys. Sanitize any user-sensitive data before passing to search endpoints.
- Cost: Document rate-limit and billing implications for grounding in README and config comments.

Files in this folder
--------------------
- api_web_search_capability_chart.md — provider/model capability matrix (seed whitelist).
- grounding_readme.md — longer guidance and examples (existing).
- implementation_plan.md — detailed plan (existing).
- wsg_functions.py — currently empty placeholder for helper functions (create helpers here or remove).
- README.md (this file) — top-level grounding README with definitions and policy (prepended explanation as requested).

If you want, I will now:
- Insert this README (done) and optionally
- Update default_config.yaml with a grounding config snippet,
- Implement a small capability-check helper in wsg_functions.py to be the starting point for provider-only grounding (requires Act mode).
