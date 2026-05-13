# Provider Setup#

## OpenAI (Responses API)#

### Supported Models#
- gpt-5, gpt-5-mini, gpt-5-nano#
- gpt-5.1, gpt-5.1-mini, gpt-5.1-preview#
- o4-mini, o3, o3-mini, o1#

### API Key#
```bash#
echo "OPENAI_API_KEY=sk-..." > FilePromptForge/.env#
```

### Usage#
```bash#
fpf --file-a doc.txt --file-b instructions.txt \
    --provider openai --model gpt-5 \
    --out result.md#
```

### Notes#
- Uses Responses API (`/v1/responses`)#
- Enforces web search via `tools=[{"type": "web_search"}]`#
- Enforces reasoning via `reasoning={"effort": "medium"}`#
- Model whitelist enforced - unknown models will fail#

---

## Google Gemini#

### Supported Models#
- gemini-2.5-pro, gemini-2.5-flash, gemini-2.5-flash-lite#
- gemini-3-pro-preview, gemini-pro-latest#
- gemini-1.5-pro, gemini-1.5-flash#

### API Key#
```bash#
echo "GOOGLE_API_KEY=..." > FilePromptForge/.env#
```

### Usage#
```bash#
fpf --file-a doc.txt --file-b instructions.txt \
    --provider google --model gemini-2.5-pro \
    --out result.md#
```

### Notes#
- Uses Gemini API (`/v1beta/models/...:generateContent`)#
- Enforces web search via `tools=[{"google_search": {}}]`#
- Enforces reasoning via `thinkingConfig` (Gemini 2.5/3.0)#
- Gemini 3.x billed per query, 2.5 billed per grounded prompt#

---

## OpenAI Deep Research (openaidp)#

### Supported Models#
- o3-deep-research#
- o4-mini-deep-research#

### API Key#
```bash#
# Uses OPENAI_API_KEY (same as OpenAI)#
```

### Usage#
```bash#
fpf --file-a doc.txt --file-b instructions.txt \
    --provider openaidp --model o3-deep-research \
    --out result.md#
```

### Notes#
- Uses same endpoint as OpenAI but different model prefix#
- Deep research models bypass concurrency/rate limits#
- Longer timeout (default 3600s = 1 hour)#

---

## Google Deep Research (googledp)#

### Supported Models#
- deep-research-pro-preview#

### API Key#
```bash#
# Uses GOOGLE_API_KEY (same as Google Gemini)#
```

### Usage#
```bash#
fpf --file-a doc.txt --file-b instructions.txt \
    --provider googledp --model deep-research-pro-preview \
    --out result.md#
```

### Notes#
- Uses Google Interactions API#
- Deep research models bypass concurrency/rate limits#
- Longer timeout (default 3600s)#

---

## OpenRouter#

### Supported Models#
- 600+ models via OpenRouter gateway#
- Format: `provider/model` (e.g., `openai/gpt-4o`, `anthropic/claude-sonnet-4`)#
- Free models: `openrouter/free` or `model:free`#

### API Key#
```bash#
echo "OPENROUTER_API_KEY=sk-or-..." > FilePromptForge/.env#
```

### Usage#
```bash#
fpf --file-a doc.txt --file-b instructions.txt \
    --provider openrouter --model openai/gpt-4o \
    --out result.md#
```

### Notes#
- **Grounding NOT enforced** (most models don't support it)#
- **Reasoning enforcement depends on model**#
- Uses OpenAI-compatible API (`/v1/chat/completions`)#
- Web search available via `openrouter:web_search` tool#

---

## Tavily Research#

### Supported Models#
- tavily/tvly-mini#
- tavily/tvly-pro#
- tavily/auto#

### API Key#
```bash#
echo "TAVILY_API_KEY=tvly-..." > FilePromptForge/.env#
```

### Usage#
```bash#
fpf --file-a doc.txt --file-b instructions.txt \
    --provider tavily --model tavily/tvly-pro \
    --out result.md#
```

### Notes#
- Built-in web search (no additional config needed)#
- Built-in reasoning#
- Uses Tavily's research API#

---

## Perplexity#

### Supported Models#
- sonar#
- sonar-deep-research#

### API Key#
```bash#
echo "PERPLEXITY_API_KEY=pplx-..." > FilePromptForge/.env#
```

### Usage#
```bash#
fpf --file-a doc.txt --file-b instructions.txt \
    --provider perplexity --model sonar \
    --out result.md#
```

### Notes#
- Built-in web search#
- Built-in reasoning#
- Uses Perplexity's API (`/v1/async/sonar`)#
- Deep research model requires `reasoning_effort` parameter#

---

## Model Selection Tips#

### For Best Grounding + Reasoning#
1. **OpenAI gpt-5** - Best overall#
2. **Google gemini-2.5-pro** - Good alternative#
3. **OpenAI o3-deep-research** - For deep research tasks#

### For Cost Efficiency#
1. **OpenAI gpt-5-mini** - Cheaper, still capable#
2. **Google gemini-2.5-flash** - Fast and affordable#
3. **OpenRouter free models** - For testing only#

### For Deep Research#
1. **o3-deep-research** (OpenAI)#
2. **deep-research-pro-preview** (Google)#
3. **sonar-deep-research** (Perplexity)#
