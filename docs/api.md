# API

The primary Python entry point is `FilePromptForge.file_handler.run`.

```python
from FilePromptForge.file_handler import run

output_path = run(
    file_a="document.txt",
    file_b="instructions.txt",
    out_path="result.md",
    provider="openai",
    model="gpt-5.6-sol",
)
```

The function accepts configuration and environment file paths, provider and
model selection, reasoning effort, token limits, timeouts, retry settings, JSON
output, and web-search options. It returns the path written on success and
raises the original configuration, validation, network, or provider error on
failure.

Run `python -m FilePromptForge --help` for the complete command-line argument
reference.

Provider modules expose payload construction, response parsing, reasoning
extraction, and provider-specific execution functions. Metering modules expose
provider-specific token extraction and cost event construction. These are
public Python modules but may evolve during the 0.x beta series.
