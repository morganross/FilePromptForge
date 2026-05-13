# API Reference#

## Python API#

### Basic Usage#

```python#
from FilePromptForge import file_handler#

# Simple run#
result_path = file_handler.run(
    file_a="document.txt",
    file_b="instructions.txt",
    out_path="result.md",
    provider="openai",
    model="gpt-5"
)
print(f"Result written to: {result_path}")
```

### Full Parameters#

```python#
result_path = file_handler.run(
    file_a="path/to/document.txt",           # Required: input document#
    file_b="path/to/instructions.txt",       # Required: prompt/instructions#
    out_path="path/to/output.md",            # Required: output file path#
    config_path="path/to/config.yaml",       # Optional: config file (default: fpf_config.yaml)#
    env_path="path/to/.env",                 # Optional: .env file (default: .env)#
    provider="openai",                        # Optional: provider name#
    model="gpt-5",                           # Optional: model name#
    reasoning_effort="medium",                # Optional: low|medium|high#
    max_completion_tokens=50000,               # Optional: max tokens#
    thinking_budget_tokens=8000,               # Optional: for some models#
    timeout=600,                              # Optional: request timeout in seconds#
    fpf_max_retries=3,                        # Optional: max retry attempts#
    fpf_retry_delay=1.0,                      # Optional: base retry delay#
    request_json=False,                        # Optional: request JSON output#
    web_search={"search_context_size": "medium"}  # Optional: web search options#
)
```

### Return Value#

Returns: `str` - Path to the output file#

Raises:#
- `grounding_enforcer.ValidationError` - If grounding/reasoning validation fails#
- `RuntimeError` - If API key missing or model not allowed#
- `Exception` - Other errors (network, API, etc.)#

---

## CLI Reference#

### Basic Usage#

```bash#
fpf --file-a document.txt --file-b instructions.txt \
    --out result.md --provider openai --model gpt-5#
```

### All Arguments#

```
Required:#
  --file-a FILE       Input document file#
  --file-b FILE       Instructions/prompt file#
  --out FILE          Output file path#
  --provider NAME     Provider name (openai, google, openrouter, etc.)#
  --model NAME        Model name#

Optional:#
  --config FILE       Path to config YAML (default: fpf_config.yaml)#
  --env FILE          Path to .env file (default: .env)#
  --reasoning-effort LEVEL   Reasoning level: low|medium|high#
  --max-completion-tokens N   Max completion tokens#
  --timeout N         Request timeout in seconds#
  --fpf-max-retries N      Max retry attempts (default: 3)#
  --fpf-retry-delay N        Base retry delay in seconds (default: 1.0)#
  --json              Request JSON output#
  --verbose, -v      Enable debug logging#
  --log-file FILE     Custom log file path#
```

### Exit Codes#

- `0` - Success (validation passed)#
- `1` - Validation failure: missing grounding only#
- `2` - Validation failure: missing reasoning only#
- `3` - Validation failure: missing both grounding and reasoning#
- `4` - Validation failure: unknown type#
- `5` - Other errors (network, API, etc.)#

---

## ValidationError#

### Attributes#

```python#
from FilePromptForge.grounding_enforcer import ValidationError#

try:#
    result = file_handler.run(...)#
except ValidationError as e:#
    print(f"Missing grounding: {e.missing_grounding}")#
    print(f"Missing reasoning: {e.missing_reasoning}")#
    print(f"Category: {e.category}")  # "validation_grounding", etc.#
    print(f"Message: {str(e)}")#
```

### Categories#

- `"validation_grounding"` - Missing grounding only#
- `"validation_reasoning"` - Missing reasoning only#
- `"validation_both"` - Missing both#
- `"validation_unknown"` - Unknown validation failure#

---

## Configuration#

### Loading Config Programmatically#

```python#
from FilePromptForge.helpers import load_config#

cfg = load_config("path/to/fpf_config.yaml")#
print(cfg.get("provider"))#
print(cfg.get("model"))#
```

### Composing Prompts#

```python#
from FilePromptForge.helpers import compose_input#

# Instructions (file_b) first, then document (file_a)#
prompt = compose_input(
    file_a="document.txt",#
    file_b="instructions.txt",#
    prompt_template=None  # or path to template with {{file_a}} and {{file_b}}#
)#
```

---

## Metering (Cost Tracking)#

### Reading Metering Events#

```python#
import json#
from pathlib import Path#

# Metering events are written to logs/metering/*.json#
for event_file in Path("logs/metering").glob("*-metering.json"):#
    event = json.loads(event_file.read_text())#
    print(f"Cost: ${event['cost']['total']:.6f}")#
    print(f"Tokens: {event['tokens']['total']}")#
```

### Cost Calculation#

```python#
from FilePromptForge.pricing.pricing_loader import load_pricing_index, find_pricing, calc_cost#

pricing_data = load_pricing_index("FilePromptForge/pricing/pricing_index.json")#
record = find_pricing(pricing_data, "openai/gpt-5")#

cost = calc_cost(
    tokens_in=1000,#
    tokens_out=500,#
    record=record#
)#
print(f"Input cost: ${cost['input_cost_usd']:.6f}")#
print(f"Output cost: ${cost['output_cost_usd']:.6f}")#
print(f"Total cost: ${cost['total_cost_usd']:.6f}")#
```

---

## Provider Adapters#

### Listing Available Providers#

```python#
import FilePromptForge.providers as providers#

print(providers.__all__)  # ['openai', 'google', 'openaidp', ...]#
```

### Using Provider Adapter Directly#

```python#
import importlib#

# Load provider module#
mod = importlib.import_module("FilePromptForge.providers.openai.fpf_openai_main")#

# Build payload#
payload, headers = mod.build_payload(
    prompt="Your prompt here",#
    cfg={"model": "gpt-5", "max_completion_tokens": 50000}#
)#

# Parse response#
text = mod.parse_response(raw_json)#
reasoning = mod.extract_reasoning(raw_json)#
```
