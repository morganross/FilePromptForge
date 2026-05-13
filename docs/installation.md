# Installation Guide

## Requirements

- Python 3.11 or higher
- pip (Python package installer)
- API keys for your chosen providers
- Internet connection (for web search grounding)

## Install from PyPI

```bash
pip install filepromptforge
```

## Install from Source

```bash
git clone https://github.com/morganross/FilePromptForge-v2.git
cd FilePromptForge-Standalone
pip install -e .
```

## Provider API Keys

Create a `.env` file in the `FilePromptForge/` directory:

```bash
# OpenAI (required for OpenAI models)
OPENAI_API_KEY=sk-...

# Google Gemini
GOOGLE_API_KEY=...

# Anthropic (via OpenRouter)
ANTHROPIC_API_KEY=...

# OpenRouter
OPENROUTER_API_KEY=...

# Perplexity
PERPLEXITY_API_KEY=...

# Tavily
TAVILY_API_KEY=...
```

**Note:** The `.env` file is the canonical source for API keys. FilePromptForge will NOT fall back to mock responses if keys are missing - it will fail with a clear error.

## Verify Installation

```bash
# Test CLI
fpf --help

# Test Python import
python -c "from FilePromptForge import file_handler; print('OK')"
```

## Quick Test

```bash
# Create test files
echo "This is a test document." > test_input.txt
echo "Summarize this document." > test_instructions.txt

# Run FPF
fpf --file-a test_input.txt --file-b test_instructions.txt \
    --out result.md --provider openai --model gpt-5-mini
```

## Troubleshooting

### "API key not found" error
- Ensure `.env` file exists in `FilePromptForge/` directory
- Check that the key name matches (e.g., `OPENAI_API_KEY` not `OPENAI_KEY`)
- Verify the key is valid by testing it directly with the provider

### "Model not allowed" error
- Check that the model is in the provider's allowed list
- For OpenAI: gpt-5, gpt-5-mini, o3, o4-mini are supported
- For Google: gemini-2.5-pro, gemini-3-pro-preview are supported

### "Grounding not detected" error
- This is intentional - FPF requires provider-side web search
- Ensure your model supports web search (most recent models do)
- Check the provider's documentation for web search support
