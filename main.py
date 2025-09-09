#!/usr/bin/env python3
"""
FilePromptForge main entrypoint.

This script reads defaults from default_config.yaml and runs the minimal CLI flow programmatically.
It uses classes from minimal_cli: PromptManager, FileHandler, APIClient, setup_logger.
Requires OPENAI_API_KEY environment variable.
"""

import os
import sys
import yaml
from pathlib import Path

try:
    from minimal_cli import PromptManager, FileHandler, APIClient, setup_logger
except Exception as e:
    print("Unable to import minimal_cli:", e)
    raise


def load_defaults(config_path: str = "default_config.yaml"):
    defaults = {
        "prompts_dir": "test/prompts",
        "input_dir": "test/input",
        "output_dir": "test/output",
        "provider": "OpenAI",
        "openai": {
            "model": "gpt-4",
            "temperature": 0.7,
            "max_tokens": 1500,
        },
    }
    if os.path.isfile(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as fh:
                user_cfg = yaml.safe_load(fh) or {}
                defaults["prompts_dir"] = user_cfg.get("prompts_dir", defaults["prompts_dir"])
                defaults["input_dir"] = user_cfg.get("input_dir", defaults["input_dir"])
                defaults["output_dir"] = user_cfg.get("output_dir", defaults["output_dir"])
                openai_cfg = user_cfg.get("openai", {})
                defaults["openai"]["model"] = openai_cfg.get("model", defaults["openai"]["model"])
                defaults["openai"]["temperature"] = openai_cfg.get("temperature", defaults["openai"]["temperature"])
                defaults["openai"]["max_tokens"] = openai_cfg.get("max_tokens", defaults["openai"]["max_tokens"])
        except Exception as e:
            print(f"Error reading config {config_path}: {e}")
    return defaults


def main():
    setup_logger(False)
    script_dir = Path(__file__).resolve().parent
    cfg_path = script_dir / "default_config.yaml"
    defaults = load_defaults(str(cfg_path))

    prompts_dir = os.path.join(str(script_dir), defaults.get("prompts_dir", "test/prompts"))
    input_dir = os.path.join(str(script_dir), defaults.get("input_dir", "test/input"))
    output_dir = os.path.join(str(script_dir), defaults.get("output_dir", "test/output"))

    openai_cfg = defaults.get("openai", {})
    model = openai_cfg.get("model", "gpt-4")
    temperature = openai_cfg.get("temperature", 0.7)
    max_tokens = openai_cfg.get("max_tokens", 1500)

    pm = PromptManager(prompts_dir)
    system_prompt = pm.load_prompts([])

    fh = FileHandler(input_dir, output_dir)
    input_files = fh.list_input_files()
    if not input_files:
        print(f"No input files found in {input_dir}. Nothing to do.")
        return 0

    client = APIClient(model, temperature, max_tokens)

    for idx, rel in enumerate(input_files):
        print(f"Processing {rel} ({idx+1}/{len(input_files)})")
        user_prompt = fh.read_file(rel)
        response = client.send_prompt(system_prompt, user_prompt)
        fh.write_file(rel, response)
        print(f"Wrote response for {rel}")

    print("All done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())