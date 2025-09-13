#!/usr/bin/env python3
"""
FilePromptForge main entrypoint (single-request mode).

This script reads defaults from default_config.yaml and runs the single-request
flow using the classes implemented in minimal_cli: PromptManager, FileHandler,
APIClient, setup_logger.

Behavior changes compared to original:
- Processes exactly one input file per run. The config key `input_file` must be set
  in default_config.yaml (or you may run the minimal CLI with --input-file).
- Grounding is enabled by default and provider-side grounding is attempted for
  every request. There is NO fallback logic.
- On provider/tool errors a .meta.json describing the error is written next to
  the expected response file and the program exits with a non-zero status.
"""

import os
import sys
import yaml
import json
from pathlib import Path
from datetime import datetime

try:
    from minimal_cli import PromptManager, FileHandler, APIClient, setup_logger
except Exception as e:
    print("Unable to import minimal_cli:", e)
    raise

# Import error metadata helper
try:
    from grounding.wsg_functions import build_error_metadata
except Exception:
    # if the grounding helpers are missing, define a minimal fallback
    def build_error_metadata(error: Exception, provider: str = "provider", model: str = ""):
        return {
            "error": {"type": type(error).__name__, "message": str(error)},
            "provider": provider,
            "model": model,
            "method": "provider-tool",
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }


def load_defaults(config_path: str = "default_config.yaml"):
    """
    Loads defaults from the provided YAML path. Returns a dict of defaults.
    Note: This function prefers the nested 'openai' mapping for model settings.
    """
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
        # single-request: input_file is expected to be set by the user/config
        "input_file": None,
        "grounding": {
            "enabled": True
        }
    }
    if os.path.isfile(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as fh:
                user_cfg = yaml.safe_load(fh) or {}
                defaults["prompts_dir"] = user_cfg.get("prompts_dir", defaults["prompts_dir"])
                defaults["input_dir"] = user_cfg.get("input_dir", defaults["input_dir"])
                defaults["output_dir"] = user_cfg.get("output_dir", defaults["output_dir"])
                defaults["input_file"] = user_cfg.get("input_file", defaults.get("input_file"))
                # grounding block
                g = user_cfg.get("grounding", {})
                if isinstance(g, dict):
                    defaults["grounding"]["enabled"] = g.get("enabled", defaults["grounding"]["enabled"])
                # openai nested
                openai_cfg = user_cfg.get("openai", {}) or {}
                defaults["openai"]["model"] = openai_cfg.get("model", defaults["openai"]["model"])
                defaults["openai"]["temperature"] = openai_cfg.get("temperature", defaults["openai"]["temperature"])
                defaults["openai"]["max_tokens"] = openai_cfg.get("max_tokens", defaults["openai"]["max_tokens"])
        except Exception as e:
            print(f"Error reading config {config_path}: {e}")
    return defaults


def _now_iso():
    return datetime.utcnow().isoformat() + "Z"


def main():
    setup_logger(False)
    script_dir = Path(__file__).resolve().parent
    cfg_path = script_dir / "default_config.yaml"
    defaults = load_defaults(str(cfg_path))

    prompts_dir = os.path.join(str(script_dir), defaults.get("prompts_dir", "test/prompts"))
    input_dir = os.path.join(str(script_dir), defaults.get("input_dir", "test/input"))
    output_dir = os.path.join(str(script_dir), defaults.get("output_dir", "test/output"))

    openai_cfg = defaults.get("openai", {}) or {}
    model = openai_cfg.get("model", "gpt-4")
    temperature = openai_cfg.get("temperature", 0.7)
    max_tokens = openai_cfg.get("max_tokens", 1500)

    grounding_cfg = defaults.get("grounding", {}) or {}
    grounding_enabled = grounding_cfg.get("enabled", True)

    pm = PromptManager(prompts_dir)
    system_prompt = pm.load_prompts([])

    fh = FileHandler(input_dir, output_dir)

    input_file = defaults.get("input_file")
    if not input_file:
        print("No input_file set in default_config.yaml. main requires 'input_file' to be set for single-request runs.")
        return 2

    # Resolve full input path
    if os.path.isabs(input_file):
        full_input = input_file
    else:
        full_input = os.path.join(input_dir, input_file)

    if not os.path.isfile(full_input):
        print(f"Input file not found: {full_input}")
        # write error meta next to expected response location
        rel = os.path.basename(full_input)
        meta_path = os.path.join(output_dir, f"response_{rel}.meta.json")
        os.makedirs(os.path.dirname(meta_path) or ".", exist_ok=True)
        err_meta = {
            "error": {"type": "InputFileNotFound", "message": f"Input file not found: {full_input}"},
            "provider": "local",
            "model": model,
            "method": "provider-tool",
            "timestamp": _now_iso(),
        }
        with open(meta_path, "w", encoding="utf-8") as mh:
            json.dump(err_meta, mh, indent=2)
        return 2

    # Read input
    try:
        with open(full_input, "r", encoding="utf-8") as fh_in:
            user_prompt = fh_in.read()
    except Exception as e:
        print(f"Failed to read input file: {e}")
        rel = os.path.basename(full_input)
        meta_path = os.path.join(output_dir, f"response_{rel}.meta.json")
        os.makedirs(os.path.dirname(meta_path) or ".", exist_ok=True)
        err_meta = build_error_metadata(e, provider="local", model=model)
        with open(meta_path, "w", encoding="utf-8") as mh:
            json.dump(err_meta, mh, indent=2)
        return 2

    client = APIClient(model, temperature, max_tokens, grounding_enabled=grounding_enabled)

    # Compute rel path used by FileHandler.write_file
    try:
        abs_input_dir = os.path.abspath(input_dir)
        abs_full_input = os.path.abspath(full_input)
        if abs_full_input.startswith(abs_input_dir):
            rel_path = os.path.relpath(abs_full_input, abs_input_dir)
        else:
            rel_path = os.path.basename(abs_full_input)
    except Exception:
        rel_path = os.path.basename(full_input)

    # Single provider attempt: no fallback. On error write .meta.json and exit non-zero.
    try:
        response_text, metadata = client.send_prompt(system_prompt, user_prompt)
    except Exception as e:
        print(f"Provider call failed: {e}")
        meta = build_error_metadata(e, provider="OpenAI", model=model)
        meta_rel = os.path.join(os.path.dirname(rel_path), f"response_{os.path.basename(rel_path)}.meta.json") if os.path.dirname(rel_path) else f"response_{os.path.basename(rel_path)}.meta.json"
        full_meta_path = os.path.join(output_dir, meta_rel)
        os.makedirs(os.path.dirname(full_meta_path) or ".", exist_ok=True)
        with open(full_meta_path, "w", encoding="utf-8") as mh:
            json.dump(meta, mh, indent=2)
        return 3

    # Write outputs
    try:
        fh.write_file(rel_path, response_text)
        meta_rel = os.path.join(os.path.dirname(rel_path), f"response_{os.path.basename(rel_path)}.meta.json") if os.path.dirname(rel_path) else f"response_{os.path.basename(rel_path)}.meta.json"
        full_meta_path = os.path.join(output_dir, meta_rel)
        os.makedirs(os.path.dirname(full_meta_path) or ".", exist_ok=True)
        if "timestamp" not in metadata:
            metadata["timestamp"] = _now_iso()
        with open(full_meta_path, "w", encoding="utf-8") as mh:
            json.dump(metadata, mh, indent=2)
    except Exception as e:
        print(f"Failed to write output files: {e}")
        return 4

    print(f"Wrote response and metadata for {rel_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
