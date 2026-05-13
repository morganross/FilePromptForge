# FilePromptForge (FPF) v2.0

**LLM-powered document generation with mandatory grounding and reasoning**

FilePromptForge is a Python toolkit that generates documents by combining prompts with LLM providers. It enforces provider-side web search (grounding) and model reasoning for all production runs.

## Features

- ✅ **Mandatory Grounding** - Provider-side web search required
- ✅ **Mandatory Reasoning** - Model thinking/reasoning required  
- ✅ **8+ Providers** - OpenAI, Google Gemini, Anthropic, OpenRouter, Tavily, Perplexity, and more
- ✅ **Intelligent Retry** - 4-layer retry with validation-specific enhancements
- ✅ **Cost Tracking** - Per-request metering and pricing
- ✅ **Concurrency** - Configurable QPS limiting and batch processing
- ✅ **No Fallbacks** - Strict error handling, no mock responses

## Quick Start

### Installation

```bash
pip install filepromptforge
```

### Basic Usage (CLI)

```bash
# Set your API key
echo "OPENAI_API_KEY=sk-..." > FilePromptForge/.env

# Run FPF
fpf --file-a document.txt --file-b instructions.txt \
    --out result.md --provider openai --model gpt-5
```

### Python API

```python
from FilePromptForge import file_handler

result_path = file_handler.run(
    file_a="document.txt",
    file_b="instructions.txt",
    out_path="result.md",
    provider="openai",
    model="gpt-5"
)
print(f"Result written to: {result_path}")
```

## Configuration

Edit `FilePromptForge/fpf_config.yaml` to set defaults:

```yaml
provider: openai
model: gpt-5
max_completion_tokens: 50000
reasoning:
  effort: medium
web_search:
  search_context_size: medium
```

## Supported Providers

| Provider | Models | Grounding | Reasoning |
|----------|--------|-----------|-----------|
| OpenAI | gpt-5, gpt-5-mini, o3, o4-mini | ✅ Required | ✅ Required |
| Google Gemini | gemini-2.5-pro, gemini-3-pro-preview | ✅ Required | ✅ Required |
| OpenAI Deep Research | o3-deep-research, o4-mini-deep-research | ✅ Required | ✅ Required |
| Anthropic (via OpenRouter) | claude-sonnet-4, etc. | ⚠️ Optional | ✅ Required |
| OpenRouter | 600+ models | ❌ Not enforced | ⚠️ Depends on model |
| Tavily | tvly-mini, tvly-pro | ✅ Built-in | ✅ Built-in |
| Perplexity | sonar, sonar-deep-research | ✅ Built-in | ✅ Built-in |

## Documentation

- [Installation Guide](docs/installation.md)
- [Configuration Reference](docs/configuration.md)
- [Provider Setup](docs/providers.md)
- [API Reference](docs/api.md)
- [Examples](examples/)

## Requirements

- Python 3.11+
- API keys for your chosen providers
- Internet connection (for web search grounding)

## License

MIT License
