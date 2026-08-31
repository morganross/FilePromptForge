# FilePromptForge

FilePromptForge (FPF) is a Python command-line tool for generating documents
from an instruction file and a source file through a selected LLM provider. It
supports provider-side web search, reasoning controls, retries, metering, and
provider-specific response handling.

This repository is the public beta. Its shipped configuration uses public
provider endpoints. Private or OpenAI-compatible gateways remain configurable
through a separate YAML configuration supplied with `--config`.

## Requirements

- Python 3.11 or newer
- An API key for the provider you select
- Internet access for provider requests and provider-side search

## Install

```bash
python -m pip install filepromptforge
```

For a source checkout:

```bash
python -m pip install -e ".[dev]"
```

## Run

```bash
fpf --file-a document.txt --file-b instructions.txt --out result.md \
  --provider openai --model gpt-5.6-sol
```

FPF reads credentials from environment variables first. A user-specific `.env`
file may also be placed in the operating system's standard application
configuration directory or supplied explicitly with `--env`. No credential is
included in this repository or its distributions.

Run `fpf --help` for all options, including configuration overrides, token
limits, timeouts, retries, JSON output, and logging.

## Providers

The public configuration includes routes for OpenAI, Anthropic, Google Gemini,
Google Deep Research, OpenRouter, Perplexity, Tavily, and OpenAI Deep Research.
Provider and model compatibility changes over time; the provider error is
returned when a selected combination is unavailable.

## Runtime files

FPF keeps mutable files outside the installed package:

- Credentials: the user configuration directory or an explicit `--env` path
- Logs: the user log directory or an explicit `--log-file`/`FPF_LOG_DIR`
- Refreshed pricing: the user cache directory or `FPF_PRICING_PATH`
- Generated output: the path supplied with `--out`

The static web-search pricing reference shipped with the package is read-only.

## Test from a fresh checkout

Run the complete suite with one command:

```bash
python scripts/test.py
```

The command creates an isolated temporary environment, builds and installs the
wheel, checks the installed CLI, and runs the repository test suite. It does
not make live provider requests and does not require API keys.

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidance and
[SECURITY.md](SECURITY.md) for private vulnerability reporting.

## License

MIT. See [LICENSE](LICENSE).
