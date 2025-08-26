Grounding / Web‑Search Integration — FilePromptForge (FPF)
=========================================================

Purpose
-------
This document summarizes how to enable "web search" / "grounding" for LLMs across three provider families: OpenAI, Google (Gemini), and OpenRouter. It explains the API parameters, which models support web search, typical request shapes, and recommended logic FPF should implement when deciding whether and how to enable grounding for a run.

Summary (at a glance)
---------------------
- OpenAI:
  - Two main paths: Responses API (tools) and Chat/Assistants/Chat Completions (tool-enabled preview models).
  - Supported models for built-in web search tools: GPT‑4.1 family, GPT‑4o family, and some o-series reasoning models (o1/o3/o4-mini) — check model metadata and availability.
  - Request-level toggles: `tools` array in Responses API (e.g., {"type": "web_search_preview"}), or `web_search_options` / `web_search` in chat endpoints for certain tool-enabled model snapshots (e.g., `gpt-4o-search-preview`, `gpt-4o-mini-search-preview`, or using `tool_choice` / `tools`).
  - Caveats: Not all models support web search; some endpoints/tool combos require specific model ids or account provisioning. Community reports show behavior and availability vary by model, API-mode (Responses vs Chat), and account/region.

- Google (Gemini) — "Grounding":
  - Google refers to web grounding tools as "Grounding with Google Search" (Bing-equivalent).
  - Grounding is exposed via their API tool parameters for Gemini models (Gemini 2.5+ families).
  - Typical flow: enable grounding in the request, optionally request URL-context fetch; Gemini will fetch and incorporate search results as context.
  - Model availability and exact flags vary across Gemini model ids (e.g., `gemini-2.5-pro`, `gemini-2.5-flash`, etc.) and may require enabling Search Grounding on your Google Cloud/Gen AI project.

- OpenRouter:
  - OpenRouter provides a model-agnostic web plugin and `:online` model suffix. Also supports model-specific `web_search_options` for models that accept them.
  - Two main options:
    1. Plugin: `plugins: [{ "id": "web", "max_results": 3, "search_prompt": "..." }]` (model-agnostic)
    2. Suffix: append `:online` to model slug (e.g., `openai/gpt-4o:online`)
  - You can tune `max_results`, `search_prompt`, and other plugin args.
  - Useful when you want a single integration across many model backends.

Detailed notes and examples
---------------------------

1) OpenAI — Responses API (recommended for tool usage)
- How it works:
  - Use Responses API (v1/responses). Include `tools` array to enable built-in tools.
  - Example enabling web search tool (Responses API):
    {
      "model": "gpt-4.1",
      "tools": [
        {
          "type": "web_search_preview",
          "search_context_size": "medium",
          "user_location": {"type":"approximate","country":"US"}
        }
      ],
      "input": "What changed in USB4 v2?"
    }
- Chat completions endpoint:
  - Some chat-only models have special search-enabled aliases like `gpt-4o-search-preview` or `gpt-4o-mini-search-preview`. For these you pass `web_search_options` or `web_search` (endpoint docs vary).
  - Example (chat/completions):
    POST /v1/chat/completions
    {
      "model": "gpt-4o-mini-search-preview",
      "messages": [{"role":"user","content":"Latest on quantum error correction?"}],
      "web_search_options": {"search_context_size":"high"}
    }
- Important considerations:
  - Responses API has explicit tool support and richer tool lifecycle (approvals, tool call outputs, background mode).
  - Some community threads show that some tool options are available in the Playground but not automatically via API for every account/model. Use explicit model ids recommended by docs and test availability.
  - When tool calls are used, the API often returns structured outputs or tool_call objects which must be handled by the client (sometimes multiple steps: model requests websearch tool -> client executes/receives tool outputs -> client passes outputs back to model via follow-up request or via built-in tool plumbing in Responses API).

2) OpenAI — logic for supported models & runtime detection
- Model list (examples from OpenAI docs / announcements):
  - GPT families with tool support: `gpt-4.1`, `gpt-4o`, `gpt-5` family, `o1`, `o3`, `o4-mini` for reasoning features.
  - Preview search models: `gpt-4o-search-preview`, `gpt-4o-mini-search-preview`
  - Deep-research native browsing: `o3-deep-research`, `o4-mini-deep-research` (these may do multi-step browsing internally).
- Implementation suggestion for FPF:
  - Maintain internal list/mapping of known web-capable model ids (seed from api_web_search_capability_chart.md).
  - At runtime, when user requests grounding:
    1. If config.provider == OpenAI:
       - If using Responses API: include `tools` array with web_search tool and set options.
       - If using Chat endpoint and model is one of the known search-preview ids, use `web_search_options` or the model alias.
    2. If the selected model is not in the whitelist, either fall back to:
       - Use external search (SerpAPI, Google Programmable Search, Bing) and pass results in prompt (safer fallback)
       - Or return a clear error / note to user
  - Provide thorough feature detection: attempt a minimal tool-enabled API call, and treat a non-supportive error (or 4xx) as "tool not available" and fallback.

3) Google Gemini — "Grounding with Google Search"
- How it works (conceptual):
  - Gemini offers search grounding as a tool; the developer enables grounding and optionally requests URL context fetch.
  - Request parameters differ from OpenAI: refer to Gemini docs; typical approach is to set "grounding" option in the request or enable a "search_grounding" tool.
- Implementation suggestion for FPF:
  - Abstract provider tool options behind a unified interface in FPF (e.g., GroundingOptions).
  - For Gemini: map GroundingOptions to Gemini-specific flags and model ids (e.g., `gemini-2.5-flash` with grounding enabled).
  - Always verify the model supports grounding via provider API (list models or model metadata) and fallback to external search if not available or if region/account disallows.

4) OpenRouter — model-agnostic plugin / :online
- How it works:
  - OpenRouter can attach a "web" plugin or `:online` suffix to a model slug to add web search.
  - Example plugin:
    {
      "model":"openai/gpt-4o:online",
      "plugins":[{"id":"web","max_results":3,"search_prompt":"Incorporate and cite these sources:"}],
      "messages":[{"role":"user","content":"What's new in USB4 v2?"}]
    }
  - Example :online suffix:
    { "model": "openai/gpt-4o:online", "messages":[...] }
- Implementation suggestion:
  - For OpenRouter provider, set `model = model + ':online'` or set `plugins` list.
  - Feed plugin args (max_results, search_prompt) from FPF configuration UI or CLI flags.
  - Use OpenRouter's catalog API to fetch available models and determine which ones accept the web plugin.

5) Fallback strategy (recommended)
- Always attempt to call provider tool only if:
  - Model chosen is known to support web search OR
  - Provider API confirms tool support (via models list or trial call).
- If tool is unavailable or errors:
  - Perform an external search using a maintained search integration (SerpAPI, Google Programmable Search, Bing Web Search API), then inject top results into the prompt (system or user) as context.
  - This approach works for any model and is robust.
- Advantage: consistent behavior across models/providers and under account/region limitations.

6) Security, privacy & approvals
- OpenAI Responses API includes MCP / remote tool approvals and may require explicit approval for remote calls (especially MCP).
- When using remote MCP or external search services, do not send user PII or sensitive data unless explicitly permitted and logged.
- Provide the user with an option to require interactive approval for tool calls (the GUI or CLI could surface this).

7) Concrete FPF integration plan (files and code)
- New folder: filepromptforge/grounding/
  - grounding_readme.me  (this file)
  - grounder.py (implementation; provider-agnostic wrapper)
  - tests/test_grounder.py (unit tests for fallbacks)
- grounder.py responsibilities:
  - Accept GroundingOptions: provider, model, max_results, search_prompt, search_provider (external fallback).
  - Detect provider capability (model metadata or test-call).
  - If provider tool supported: assemble appropriate request (OpenAI Responses tools or OpenRouter plugin or Gemini grounding params) and return final model response (handling tool_call outputs if needed).
  - If provider tool not supported or errors: run external search (configurable) and inject top results into system prompt; call chosen model normally.
  - Return structured result: { response_text, sources: [ ... ], method: "provider-tool" | "external-search" }
- Example CLI flags to add:
  --grounding          enable grounding/websearch
  --grounding_provider openai|openrouter|google|external
  --max_results N
  --search_prompt "..."
  --external_search_api serpapi|bing|google_cs

8) Example: OpenAI Responses API minimal request with web_search_preview
- Responses API (Python style; concept):
  from openai import OpenAI
  client = OpenAI(api_key=...)
  response = client.responses.create(
      model="gpt-4.1",
      tools=[{
         "type":"web_search_preview",
         "search_context_size":"medium",
         "max_results":3
      }],
      input="Summarize today's major AI news with sources."
  )
  # Parse response.output for tool_call items and final output_text
- If using chat/completions with search-preview model:
  POST /v1/chat/completions
  {
    "model":"gpt-4o-mini-search-preview",
    "messages":[{"role":"user","content":"Latest AI news?"}],
    "web_search_options":{"search_context_size":"high"}
  }

9) Example: OpenRouter plugin (JSON)
  {
    "model":"openai/gpt-4o:online",
    "plugins":[{"id":"web","max_results":5,"search_prompt":"Cite sources:"}],
    "messages":[{"role":"user","content":"What changed in USB4 v2?"}]
  }

10) Google Gemini grounding (concept)
- Use Gemini API request shape to enable grounding. Typically:
  - Include a grounding option or tool param (consult Gemini docs for exact parameter names).
  - Optionally request URL context fetch or set search depth.
- Because vendor docs change often, implement a small provider adapter module that maps FPF GroundingOptions -> provider request.

11) Model capability list and FPF logic
- Initial whitelist (seed from repo chart and official docs):
  - OpenAI: gpt-4.1 family, gpt-4o family, o1/o3/o4-mini (reasoning models), preview search models (gpt-4o-search-preview, gpt-4o-mini-search-preview), deep-research models (o3-deep-research, o4-mini-deep-research)
  - Google: gemini-2.5 family (gemini-2.5-pro, gemini-2.5-flash, gemini-2.5-flash-lite, gemini-live-2.5-flash-preview)
  - OpenRouter: depends on catalog; OpenRouter `:online` plugin can add search to many model slugs
- FPF runtime logic:
  1. If --grounding not set: skip grounding.
  2. If provider supports built-in grounding for chosen model: call provider tool (Responses API preferred).
  3. If provider tool unsupported or returns an error: run external search, inject top-k snippets into the system prompt, continue with normal model call.
  4. Save fetched sources and the "method" used to the response_<file> output for later auditing.

References and sources
----------------------
- filepromptforge/api_web_search_capability_chart.md (this repository)
- OpenAI docs:
  - Responses API / Tools / Web Search: https://platform.openai.com/docs/guides/tools-web-search
  - Model pages (gpt-4.1, gpt-4o, o-series)
  - Responses API news: https://openai.com/index/new-tools-and-features-in-the-responses-api/
- OpenAI community threads (evidence of model/tool availability and caveats): OpenAI Community forum (web-search threads)
- OpenRouter docs and examples (plugins and :online suffix)
- Google Gemini docs (Grounding) — consult Google Gen AI docs for exact parameter names in your target account/region
- Azure docs: Responses API and MCP examples (useful for enterprise / Azure-hosted deployment)

Notes & next steps for implementation
-------------------------------------
1. Create grounder.py provider adapters:
   - openai_adapter (Responses API / Chat fallback)
   - openrouter_adapter (plugins / :online)
   - google_adapter (Gemini grounding options)
   - external_search_adapter (SerpAPI / Bing / Google Programmable Search)
2. Add CLI flags / config options for grounding (see section 7).
3. Include a feature detection call at runtime before enabling tools to avoid unexplained failures.
4. Add tests and logging: record which method produced the result and the search snippets returned.
5. Update README and GUI (installer) to offer grounding configuration options (keys, provider, enabled flag). The GUI was left unchanged per earlier instruction; update only CLI/config first.

End of grounding_readme.me
