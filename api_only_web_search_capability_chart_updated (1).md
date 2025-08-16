# API‑Only Web‑Search Capability Chart (no agents/MCP)

**Legend**\
**Native Web Search** = model itself fetches live web pages via the provider’s API.\
**API‑based Web Search** = provider offers a first‑party search/browsing tool/connector you can enable in API calls.

| Provider        | Model(s)                                                      | Native Web Search? | API‑based Web Search? (provider tool) | Notes                                                                                                                                                  |
| --------------- | ------------------------------------------------------------- | ------------------ | ------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **OpenAI**      | **o4‑mini**                                                   | No                 | No                                    | Base model; use external search API if needed.                                                                                                         |
|                 | **o4‑mini‑deep‑research**                                     | **Yes**            | No                                    | Deep Research model conducts its own multi‑step browsing and returns citations.                                                                        |
|                 | **o3‑deep‑research**                                          | **Yes**            | No                                    | Deep Research model conducts its own multi‑step browsing and returns citations.                                                                        |
|                 | **gpt‑4.1**                                                   | No                 | **Yes**                               | Enable provider web‑search tool in the Responses API.                                                                                                  |
|                 | **gpt‑4o**                                                    | No                 | **Yes**                               | Enable provider web‑search tool in the Responses API.                                                                                                  |
|                 | **gpt‑5**                                                     | No                 | **Yes**                               | Supports provider web‑search tool via Responses API (tooling availability may evolve).                                                                 |
|                 | **gpt‑5‑mini**                                                | No                 | **Yes**                               | Smaller, cheaper variant; supports provider web‑search tool via Responses API.                                                                         |
|                 | **gpt‑5‑nano**                                                | No                 | **Yes**                               | Fastest/cheapest variant; supports provider web‑search tool via Responses API.                                                                         |
|                 | **gpt‑5‑thinking**                                            | No                 | **Yes**                               | Reasoning‑optimized variant; supports provider web‑search tool via Responses API.                                                                      |
|                 | **gpt‑5‑thinking‑mini**                                       | No                 | **Yes**                               | Smaller thinking variant; supports provider web‑search tool via Responses API.                                                                         |
|                 | **gpt‑5‑thinking‑nano**                                       | No                 | **Yes**                               | Smallest thinking variant; supports provider web‑search tool via Responses API.                                                                        |
| **Google**      | **Gemini 2.5+**                                               | No                 | **Yes**                               | “Grounding with Google Search” tool; optional URL‑context fetch.                                                                                       |
|                 | **Gemini 2.5 Pro**                                            | No                 | **Yes**                               | Search Grounding supported; URL Context supported; model id `gemini-2.5-pro`.                                                                          |
|                 | **Gemini 2.5 Flash**                                          | No                 | **Yes**                               | Search Grounding supported; model id `gemini-2.5-flash`.                                                                                               |
|                 | **Gemini 2.5 Flash‑Lite**                                     | No                 | **Yes**                               | Search Grounding + URL Context supported; model id `gemini-2.5-flash-lite`.                                                                            |
|                 | **Gemini 2.5 Flash Live**                                     | No                 | **Yes**                               | Search supported in Live API; model id `gemini-live-2.5-flash-preview`.                                                                                |
|                 | **Gemini 2.5 Flash Native Audio**                             | No                 | **Yes**                               | Search Grounding supported in Live API; model ids `gemini-2.5-flash-preview-native-audio-dialog`, `gemini-2.5-flash-exp-native-audio-thinking-dialog`. |
| **DeepSeek**    | **DeepSeek R1 (reasoner), DeepSeek V3**                       | No                 | No                                    | Official API doesn’t expose built‑in browsing; use your own search API if required.                                                                    |
| **xAI**         | **Grok 4**                                                    | **Yes**            | No                                    | Live Search is native via the chat‑completions API (off by default; toggleable per call).                                                              |
| **Perplexity**  | **Sonar / Sonar Pro / Sonar Reasoning / Sonar Deep Research** | **Yes**            | No                                    | “Browse”/search‑grounded models with citations; designed for live web retrieval.                                                                       |
| **Anthropic**   | **Claude 3.7 / 3.5 family**                                   | No                 | **Yes**                               | First‑party *web\_search* tool in the Messages API with automatic citations.                                                                           |
|                 |                                                               |                    |                                       |                                                                                                                                                        |
| **Mistral**     | **All current chat models**                                   | No                 | **Yes**                               | Built‑in *websearch* connector (standard & premium) available via API.                                                                                 |
|                 |                                                               |                    |                                       |                                                                                                                                                        |
|                 |                                                               |                    |                                       |                                                                                                                                                        |
| **Moonshot AI** | **Kimi K2**                                                   | No                 | **Yes**                               | Built‑in `$web_search` tool callable from the API.                                                                                                     |
|                 |                                                               |                    |                                       |                                                                                                                                                        |

> This chart intentionally focuses **only** on capabilities available through provider APIs. It excludes any third‑party agents, MCP, or custom toolchains.



## Deep Research (API‑only)

**What we mean by “deep research.”** In this context, deep research = the model autonomously plans multi‑step web queries, fetches/reads many sources, tracks what’s been covered, and synthesizes a long, cited write‑up — all from a single API call (you don’t wire separate steps yourself).

### Models that are *natively* deep‑research (choose the model; no extra flag)

- **OpenAI — o3‑deep‑research**
- **OpenAI — o4‑mini‑deep‑research**
- **Perplexity — sonar‑deep‑research**

These models run a built‑in multi‑step research pipeline (iterative search → read → analyze → cite → synthesize). Use them when you want comprehensive, multi‑source reports with citations from one request.

### “Deep research as a flag” (do any models expose a dedicated switch?)

- **No explicit, provider‑defined **``** flag** exists for the other models in this chart as of now. Instead, they expose **first‑party web‑search tools** (e.g., OpenAI web\_search, Anthropic web search, Google Search Grounding, xAI Live Search, Mistral/Cohere/Zhipu/Baidu/Tencent/Moonshot/iFLYTEK search tools).
- You can *approximate* deeper runs by tuning each provider’s knobs (examples):
  - **xAI**: `search_parameters.mode` (`auto`/`on`) and limits like `max_search_results`; optional citations.
  - **OpenAI / Anthropic / Google**: enable the provider search tool and prompt for breadth/iterations; these perform search‑augmented answers but are **not** the same pipeline as the native deep‑research models above.

### Practical guidance

- Pick a **native deep‑research model** for long, multi‑source briefs or due‑diligence‑style reports (less glue code; built‑in citations and coverage tracking).
- Use a **provider web‑search tool** on non‑DR models when you want fast, search‑grounded answers without the full multi‑step research loop. \
  \

  ### OpenRouter — Web Search (API)

**Short answer:** Yes. OpenRouter provides a first‑party *Web Search* capability you can attach to **any** model via its **web** plugin or by appending `:online` to the model slug. It also exposes “non‑plugin” web search controls for models with native browsing.

**Two ways to add web search**

1. **Model‑agnostic Web plugin** (powered by Exa). Enable with `plugins: [{ "id": "web" }]` or use the `:online` suffix. You can tune `max_results` (default 5) and the `search_prompt`. **Pricing:** \$4 per 1,000 results (default 5 ⇒ up to \~\$0.02 per request), billed via OpenRouter credits.

**Example (quick enable):**

```json
{ "model": "openai/gpt-4o:online", "messages": [{ "role": "user", "content": "What changed in USB4 v2?" }] }
```

**Example (customized plugin):**

```json
{
  "model": "openai/gpt-4o:online",
  "plugins": [
    { "id": "web", "max_results": 3, "search_prompt": "Incorporate and cite these sources:" }
  ]
}
```

2. **Non‑plugin web search** (for models with native browsing). Control the amount of retrieved context with `web_search_options.search_context_size` (`low` / `medium` / `high`).

```json
{
  "model": "openai/gpt-4.1",
  "messages": [{ "role": "user", "content": "Latest on quantum error correction" }],
  "web_search_options": { "search_context_size": "high" }
}
```

**Citations / parsing:** OpenRouter standardizes source citations in responses via `annotations` with `type: "url_citation"`, so you can render links consistently.

> You can also wire your own search via standard tool/function calling, but the plugin / `:online` path is the simplest provider‑hosted option. 
