# Configuration Reference

FilePromptForge uses `fpf_config.yaml` for default settings. This file is read from the `FilePromptForge/` directory.

## Basic Configuration

```yaml
# Provider and model
provider: openai
model: gpt-5

# Token limits
max_completion_tokens: 50000

# Reasoning configuration
reasoning:
  effort: medium  # low | medium | high

# Web search settings
web_search:
  search_context_size: medium  # low | medium | high
  search_prompt: "Perform a focused web search..."
```

## Concurrency Settings

```yaml
concurrency:
  enabled: true
  max_concurrency: 46
  qps: 0.9  # queries per second
  retry:
    base_delay_ms: 500
    jitter: full
    max_delay_ms: 6000
    max_retries: 2
  timeout_seconds: 600
```

## Provider URLs

```yaml
provider_urls:
  google: https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-pro:generateContent
  openai: https://api.openai.com/v1/responses
  perplexity: https://api.perplexity.ai/v1/async/sonar
  tavily: https://api.tavily.com/research
  openaidp: https://api.openai.com/v1/responses
  googledp: https://generativelanguage.googleapis.com/v1beta/interactions
  anthropic: https://api.anthropic.com/v1/messages
  openrouter: https://openrouter.ai/api/v1/chat/completions
```

## Provider-Specific Settings

```yaml
providers:
  perplexity:
    timeout_seconds: 3600
  openaidp:
    timeout_seconds: 3600
  googledp:
    timeout_seconds: 3600
```

## Test Configuration

```yaml
test:
  file_a: test/input/sample_utf8.txt
  file_b: test/prompts/standard_prompt.txt
  out: test/output/<file_b_stem>.<model_name>.fpf.response.md
```

## Important Notes

- **Grounding and reasoning are NOT configurable** - they are always enforced
- Any settings in `fpf_config.yaml` that would disable grounding or reasoning are ignored
- The `provider_urls` section maps provider names to their API endpoints
- Concurrency settings control batch processing via `scheduler.py`

## Environment Variables

FilePromptForge reads API keys from the `.env` file in this order:

1. `OPENAI_API_KEY` - OpenAI and OpenAI Deep Research
2. `GOOGLE_API_KEY` - Google Gemini and Google Deep Research  
3. `ANTHROPIC_API_KEY` - Anthropic (via OpenRouter)
4. `OPENROUTER_API_KEY` - OpenRouter
5. `PERPLEXITY_API_KEY` - Perplexity
6. `TAVILY_API_KEY` - Tavily

## Prompt Template

```yaml
prompt_template: null  # or path to template file

# If using template, it may contain:
# {{file_a}} - replaced with file_a content
# {{file_b}} - replaced with file_b content
```

Example template:
```
Instructions: {{file_b}}

Document to analyze:
{{file_a}}
```
