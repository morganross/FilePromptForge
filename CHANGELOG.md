# Changelog#

## [2.0.0] - 2026-05-13#

### Added (from acm2 integration)#
- Mandatory grounding enforcement (web search required)#
- Mandatory reasoning enforcement (thinking required)#
- Multi-provider support (8 providers: OpenAI, Google, Anthropic, OpenRouter, Tavily, Perplexity, etc.)#
- Intelligent retry system with exit codes (0-5)#
- Metering and cost tracking with 6 decimal precision#
- Pricing system with 1,200+ model prices#
- Concurrency support with QPS limiting#
- Run resume and crash recovery#
- Timeout handling with grace period#
- Perplexity provider support#
- GPT-5.4 model support#
- Google Gemini 3.0 support#
- Deep Research providers (OpenAI DP, Google DP)#
- Validation error classification system#
- Per-run validation logging#
- Provider-specific token extraction#
- Web search pricing (per query, per grounded prompt)#

### Changed#
- Completely rewritten from standalone v1.x#
- `file_handler.run()` is now the main entry point#
- CLI changed from `minimal_cli.py` to `fpf_main.py`#
- Configuration format updated to `fpf_config.yaml`#
- Provider adapters now enforce grounding and reasoning#
- HTTP requests use urllib (no extra dependencies)#
- Error handling uses intelligent classification and retry#

### Removed#
- Fallback logic and mock responses#
- Installer GUI (Tkinter-based)#
- Legacy `ARCHIVE_main.py`#
- `minimal_cli.py` (replaced by `fpf_main.py`)#
- Backup files (`.bak-*`)#

### Security#
- No fallback to mock responses - strict error handling#
- API keys loaded only from `.env` file or environment#
- No sensitive data in logs (redacted headers)#

---

## [1.0.0] - 2025-09-13#

### Added (original standalone)#
- Initial GPT processor#
- Provider-side grounding (optional)#
- Multi-provider support (OpenAI, OpenRouter, Google)#
- Minimal CLI (`minimal_cli.py`)#
- Environment variable support (`.env`)#
- Default config YAML (`default_config.yaml`)#
- Installer GUI (Tkinter-based)#
- Basic prompt management#
- File processing (input → LLM → output)#

### Features#
- Optional grounding (web search)#
- Mock responses if no API key#
- Fallback logic for API failures#
- Single-request mode only#
