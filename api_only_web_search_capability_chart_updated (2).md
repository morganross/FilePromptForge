# API‑Only Web‑Search Capability Chart (no agents/MCP)

**Legend**\
**Native Web Search** = model itself fetches live web pages via the provider’s API.\
**API‑based Web Search** = provider offers a first‑party search/browsing tool/connector you can enable in API calls.\


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

In this context, deep research = the model autonomously plans multi‑step web queries, fetches/reads many sources, tracks what’s been covered, and synthesizes a long, cited write‑up — all from a single API call (Behind the scenes DR is multi agent on the server side, but they present as one-shot to the api user).

### Models that are *natively* deep‑research (choose the model; no extra flag)

- **OpenAI — o3‑deep‑research**
- **OpenAI — o4‑mini‑deep‑research**
- **Perplexity — sonar‑deep‑research**

Deep research as a flag does not exist

### OpenRouter — Web Search (API)

OpenRouter provides a first‑party *Web Search* capability you can attach to **any** model via its **web** plugin or by appending `:online` to the model slug. It also exposes “non‑plugin” web search controls for models with native browsing.

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



## Daily Free API Usage — OpenRouter Models

> Free usage on OpenRouter applies to model variants that end with `:free`. Default cap is **50 requests/day** and **20 RPM**; if you’ve purchased **≥ \$10** credits, the cap increases to **1,000 requests/day** for `:free` models.

| Model (slug)                                    | Provider     | Daily Free Limit                       | RPM | How to call                                               | Notes                                              |
| ----------------------------------------------- | ------------ | -------------------------------------- | --- | --------------------------------------------------------- | -------------------------------------------------- |
| deepseek/deepseek-chat-v3-0324\:free            | DeepSeek     | 50/day (1,000/day with ≥ \$10 credits) | 20  | `model: "deepseek/deepseek-chat-v3-0324:free"`            | General chat model; good quality for a free tier.  |
| deepseek/deepseek-r1\:free                      | DeepSeek     | 50/day (1,000/day with ≥ \$10 credits) | 20  | `model: "deepseek/deepseek-r1:free"`                      | Reasoning model (R1) free variant.                 |
| deepseek/deepseek-r1-0528\:free                 | DeepSeek     | 50/day (1,000/day with ≥ \$10 credits) | 20  | `model: "deepseek/deepseek-r1-0528:free"`                 | Dated R1 build often available as free.            |
| qwen/qwen3-coder\:free                          | Alibaba Qwen | 50/day (1,000/day with ≥ \$10 credits) | 20  | `model: "qwen/qwen3-coder:free"`                          | Code-focused model.                                |
| qwen/qwen3-4b\:free                             | Alibaba Qwen | 50/day (1,000/day with ≥ \$10 credits) | 20  | `model: "qwen/qwen3-4b:free"`                             | Lightweight general model.                         |
| mistralai/mistral-7b-instruct\:free             | Mistral      | 50/day (1,000/day with ≥ \$10 credits) | 20  | `model: "mistralai/mistral-7b-instruct:free"`             | Classic small instruct model.                      |
| mistralai/mistral-small-24b-instruct-2501\:free | Mistral      | 50/day (1,000/day with ≥ \$10 credits) | 20  | `model: "mistralai/mistral-small-24b-instruct-2501:free"` | Newer small/fast model variant.                    |
| meta-llama/llama-3.1-405b-instruct\:free        | Meta         | 50/day (1,000/day with ≥ \$10 credits) | 20  | `model: "meta-llama/llama-3.1-405b-instruct:free"`        | Very large instruct model when available.          |
| google/gemma-3-12b-it\:free                     | Google       | 50/day (1,000/day with ≥ \$10 credits) | 20  | `model: "google/gemma-3-12b-it:free"`                     | Open lightweight model (instruction-tuned).        |
| nvidia/llama-3.3-nemotron-super-49b-v1\:free    | NVIDIA       | 50/day (1,000/day with ≥ \$10 credits) | 20  | `model: "nvidia/llama-3.3-nemotron-super-49b-v1:free"`    | NVIDIA-optimized large model.                      |
| venice/uncensored\:free                         | Venice       | 50/day (1,000/day with ≥ \$10 credits) | 20  | `model: "venice/uncensored:free"`                         | Community model that periodically appears as free. |

*Availability of **``** variants changes over time. To find current options: filter the OpenRouter model catalog by ****Pricing = FREE**** or search for **``**.*

---

## Daily Free API Usage — Non‑OpenRouter (Direct Providers)

> Provider-run APIs that offer **documented daily free usage**. Limits can change; always check the provider’s rate-limit page.

| Provider          | Model                      | Free Tier RPD (Requests/Day) | RPM | Notes                                                                             |
| ----------------- | -------------------------- | ---------------------------- | --- | --------------------------------------------------------------------------------- |
| Google Gemini API | Gemini 2.5 Pro             | **100 RPD**                  | 5   | Free-tier tokens; Search Grounding not free on this model’s free tier.            |
| Google Gemini API | Gemini 2.5 Flash           | **250 RPD**                  | 10  | Free-tier tokens; Search Grounding free up to **500 RPD** (shared w/ Flash‑Lite). |
| Google Gemini API | Gemini 2.5 Flash‑Lite      | **1,000 RPD**                | 15  | Free-tier tokens; Search Grounding free up to **500 RPD** (shared w/ Flash).      |
| Google Gemini API | Gemini 2.0 Flash           | **200 RPD**                  | 15  | Free-tier tokens; Live API also listed free in pricing page.                      |
| Google Gemini API | Gemini 2.0 Flash‑Lite      | **200 RPD**                  | 30  | Free-tier tokens.                                                                 |
| Google Gemini API | Gemma 3 / 3n (open models) | **14,400 RPD**               | 30  | Text-only open models hosted under Gemini API free tier.                          |
| Google Gemini API | Gemini Embedding           | **1,000 RPD**                | 100 | Embeddings model under free tier.                                                 |

*Source: Google Gemini API pricing & rate-limits pages (Free Tier table). Live/preview models may have separate session-based limits.*

