"""Batch processing example using scheduler"""

from FilePromptForge import scheduler
from FilePromptForge.scheduler import RunSpec

# Define batch specs
specs = [
    RunSpec(
        id="run1",
        provider="openai",
        model="gpt-5-mini",
        file_a="doc1.txt",
        file_b="instructions.txt",
        out="output1.md"
    ),
    RunSpec(
        id="run2",
        provider="google",
        model="gemini-2.5-flash",
        file_a="doc2.txt",
        file_b="instructions.txt",
        out="output2.md"
    ),
]

# Load config
config_path = "FilePromptForge/fpf_config.yaml"
env_path = "FilePromptForge/.env"

# Concurrency config
concurrency_cfg = {
    "enabled": True,
    "max_concurrency": 4,
    "qps": 0.5,
    "retry": {
        "max_retries": 2,
        "base_delay_ms": 500,
        "max_delay_ms": 6000,
        "jitter": "full"
    },
    "timeout_seconds": 600
}

# Run batch
results = scheduler.run_many(specs, config_path, env_path, concurrency_cfg)

for result in results:
    print(f"{result['id']}: {result.get('path', 'ERROR') or result.get('error', 'unknown')}")
