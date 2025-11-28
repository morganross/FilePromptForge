#!/usr/bin/env python3
"""Minimal FilePromptForge — OpenAI-only CLI (single-request mode)

Behavior changes:
- Processes exactly one input file per run. Use --input-file to specify the input file
  (path may be absolute or relative to the configured input_dir).
- Loads filepromptforge/default_config.yaml if present and uses it as defaults;
  CLI args override config values.
- Grounding is enabled by default and the client will perform a single provider-side
  request. There is NO fallback logic. If the provider request fails, a .meta.json
  containing error metadata is written next to the expected response file and the
  program exits with a non-zero status.
"""

import os
import sys
import argparse
import logging
import json
import yaml
from datetime import datetime
from typing import List, Tuple, Dict, Any, Optional
from pathlib import Path
from dotenv import load_dotenv

# Load .env from the script directory if present
script_dir = Path(__file__).resolve().parent
dotenv_path = script_dir / ".env"
if dotenv_path.exists():
    load_dotenv(dotenv_path)
else:
    try:
        load_dotenv()
    except Exception:
        pass

try:
    from openai import OpenAI
except Exception as e:
    print("Missing dependency: openai. Install with: pip install -r requirements.txt")
    raise

from grounding.wsg_functions import canonicalize_provider_response, build_error_metadata

LOG = None


def setup_logger(verbose: bool = False):
    global LOG
    LOG = logging.getLogger("fpf_minimal")
    LOG.setLevel(logging.DEBUG if verbose else logging.INFO)
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG if verbose else logging.INFO)
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    ch.setFormatter(formatter)
    if not LOG.handlers:
        LOG.addHandler(ch)


class PromptManager:
    def __init__(self, prompts_dir: str):
        self.prompts_dir = prompts_dir

    def load_prompts(self, prompt_files: List[str]) -> str:
        prompts = []
        if not prompt_files:
            try:
                files = sorted(os.listdir(self.prompts_dir))
            except FileNotFoundError:
                raise FileNotFoundError(f"Prompts directory not found: {self.prompts_dir}")
            prompt_files = [f for f in files if os.path.isfile(os.path.join(self.prompts_dir, f))]
        for fname in prompt_files:
            path = os.path.join(self.prompts_dir, fname)
            with open(path, "r", encoding="utf-8") as fh:
                content = fh.read()
                prompts.append(content)
        return "\n".join(prompts)


class FileHandler:
    def __init__(self, input_dir: str, output_dir: str):
        self.input_dir = input_dir
        self.output_dir = output_dir

    def list_input_files(self) -> List[str]:
        # kept for compatibility but not used in single-request mode
        files = []
        for root, _, filenames in os.walk(self.input_dir):
            for fname in filenames:
                full = os.path.join(root, fname)
                rel = os.path.relpath(full, self.input_dir)
                files.append(rel)
        return sorted(files)

    def read_file(self, rel_path: str) -> str:
        full = os.path.join(self.input_dir, rel_path)
        with open(full, "r", encoding="utf-8") as fh:
            return fh.read()

    def write_file(self, rel_path: str, content: str):
        out_rel = os.path.join(os.path.dirname(rel_path), f"response_{os.path.basename(rel_path)}") if os.path.dirname(rel_path) else f"response_{os.path.basename(rel_path)}"
        full_out = os.path.join(self.output_dir, out_rel)
        os.makedirs(os.path.dirname(full_out), exist_ok=True)
        with open(full_out, "w", encoding="utf-8") as fh:
            fh.write(content)


class APIClient:
    def __init__(self, model: str, temperature: float, max_tokens: int, grounding_enabled: bool = True, base_url: Optional[str] = None):
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY not set in environment. This tool requires a valid OpenAI API key.")
        if base_url:
            self.client = OpenAI(api_key=api_key, base_url=base_url)
        else:
            self.client = OpenAI(api_key=api_key)
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.grounding_enabled = grounding_enabled

    def send_prompt(self, system_prompt: str, user_prompt: str) -> Tuple[str, Dict[str, Any]]:
        """
        Perform a single provider-side request. No fallback logic is performed.
        Returns: (text, metadata_dict)
        On error: raise the caught exception to caller so caller can write error metadata.
        """
        messages_input = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        if self.grounding_enabled:
            # Use responses.create for grounded calls (as explicitly chosen).
            # Rely on LiteLLM to map "web_search_preview" tool if model supports it.
            resp = self.client.responses.create(
                model=self.model,
                input=messages_input, # Use 'input' parameter which can take messages
                tools=[{"type": "web_search_preview"}], # Explicitly ask for web search
                tool_choice="auto",
                temperature=self.temperature,
                max_output_tokens=self.max_tokens # Responses API uses max_output_tokens
            )
        else:
            # Non-grounded calls still use chat.completions
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=messages_input,
                temperature=self.temperature,
                max_tokens=self.max_tokens
            )
        # Canonicalize provider response (best-effort)
        metadata = canonicalize_provider_response(resp, provider="OpenAI", model=self.model)
        text = metadata.get("text", "")
        return text, metadata


def load_config_file(script_dir: Path) -> Dict:
    cfg_path = script_dir / "default_config.yaml"
    if not cfg_path.exists():
        return {}
    try:
        with open(cfg_path, "r", encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except Exception:
        return {}


def _now_iso():
    return datetime.utcnow().isoformat() + "Z"


def main(argv=None):
    parser = argparse.ArgumentParser(description="FilePromptForge - Minimal OpenAI-only CLI (single-request)")
    parser.add_argument("--prompts", nargs="+", help="Ordered list of prompt filenames (from prompts directory). If omitted, all files in prompts_dir are used in sorted order.", default=None)
    parser.add_argument("--prompts-dir", help="Directory containing prompt files.", default=None)
    parser.add_argument("--input-file", help="Path to single input file to process (absolute or relative to script directory).", default=None)
    parser.add_argument("--output-dir", help="Directory for responses.", default=None)
    parser.add_argument("--model", help="OpenAI model id to use.", default=None)
    parser.add_argument("--temperature", type=float, help="Temperature for the model.", default=None)
    parser.add_argument("--max-tokens", type=int, help="Max tokens for completion.", default=None)
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging.")
    args = parser.parse_args(argv)

    setup_logger(args.verbose)
    LOG.info("Starting FilePromptForge (minimal OpenAI-only) [single-request mode]")

    # Load config and treat it as defaults; CLI args override config
    cfg = load_config_file(script_dir)
    prompts_dir = args.prompts_dir or cfg.get("prompts_dir", "test/prompts")
    # resolve relative prompts_dir against the package script dir
    if prompts_dir and not os.path.isabs(prompts_dir):
        prompts_dir = os.path.join(str(script_dir), prompts_dir)
    output_dir = args.output_dir or cfg.get("output_dir", "test/output")
    if output_dir and not os.path.isabs(output_dir):
        output_dir = os.path.join(str(script_dir), output_dir)

    openai_cfg = cfg.get("openai", {}) or {}
    model = args.model or openai_cfg.get("model", "gpt-4")
    temperature = args.temperature if args.temperature is not None else openai_cfg.get("temperature", 0.7)
    max_tokens = args.max_tokens if args.max_tokens is not None else openai_cfg.get("max_tokens", 1500)

    grounding_cfg = cfg.get("grounding", {}) or {}
    grounding_enabled = grounding_cfg.get("enabled", True)
    llm_base_url = cfg.get("llm_endpoint_url")

    pm = PromptManager(prompts_dir)
    system_prompt = pm.load_prompts(args.prompts or [])
    
    # FileHandler expects an input_dir when reading by relative paths; in single-file mode
    # we interpret relative input_file paths relative to the package script directory.
    fh = FileHandler(str(script_dir), output_dir)

    # Determine input file
    input_file_arg = args.input_file or cfg.get("input_file")
    if not input_file_arg:
        LOG.error("No input file specified. Provide --input-file or set input_file in default_config.yaml")
        return 2

    # Determine full path to input file with normalization:
    # - Accept absolute paths as-is
    # - If path starts with the package dir name (e.g., "filepromptforge/..."), strip that prefix
    # - Try relative to current working directory; if not found, try relative to the script directory
    if os.path.isabs(input_file_arg):
        full_input = input_file_arg
    else:
        norm_rel = os.path.normpath(input_file_arg)
        parts = norm_rel.split(os.sep)
        pkg_name = os.path.basename(str(script_dir))
        if parts and parts[0].lower() == pkg_name.lower():
            norm_rel = os.path.join(*parts[1:]) if len(parts) > 1 else ""
        candidate_cwd = os.path.abspath(norm_rel) if norm_rel else None
        candidate_pkg = os.path.join(str(script_dir), norm_rel) if norm_rel else str(script_dir)
        if candidate_cwd and os.path.isfile(candidate_cwd):
            full_input = candidate_cwd
        else:
            full_input = candidate_pkg

    if not os.path.isfile(full_input):
        LOG.error("Input file not found: %s", full_input)
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

    # Read content
    try:
        with open(full_input, "r", encoding="utf-8") as fh_in:
            user_prompt = fh_in.read()
    except Exception as e:
        LOG.error("Failed to read input file: %s", e)
        rel = os.path.basename(full_input)
        meta_path = os.path.join(output_dir, f"response_{rel}.meta.json")
        os.makedirs(os.path.dirname(meta_path) or ".", exist_ok=True)
        err_meta = build_error_metadata(e, provider="local", model=model)
        with open(meta_path, "w", encoding="utf-8") as mh:
            json.dump(err_meta, mh, indent=2)
        return 2

    client = APIClient(model, temperature, max_tokens, grounding_enabled=grounding_enabled, base_url=llm_base_url)

    # Compute rel path used by FileHandler.write_file
    try:
        # Use the package script directory as the base for relative paths
        abs_input_dir = os.path.abspath(str(script_dir))
        abs_full_input = os.path.abspath(full_input)
        if abs_full_input.startswith(abs_input_dir):
            rel_path = os.path.relpath(abs_full_input, abs_input_dir)
        else:
            rel_path = os.path.basename(abs_full_input)
    except Exception:
        rel_path = os.path.basename(full_input)

    # Call provider (single attempt; no fallback). On error write .meta.json and exit non-zero.
    try:
        response_text, metadata = client.send_prompt(system_prompt, user_prompt)
    except Exception as e:
        LOG.error("Provider call failed: %s", e)
        meta = build_error_metadata(e, provider="OpenAI", model=model)
        # write meta json next to the expected response file
        meta_rel = os.path.join(os.path.dirname(rel_path), f"response_{os.path.basename(rel_path)}.meta.json") if os.path.dirname(rel_path) else f"response_{os.path.basename(rel_path)}.meta.json"
        full_meta_path = os.path.join(output_dir, meta_rel)
        os.makedirs(os.path.dirname(full_meta_path) or ".", exist_ok=True)
        with open(full_meta_path, "w", encoding="utf-8") as mh:
            json.dump(meta, mh, indent=2)
        return 3

    # Write the response and metadata
    try:
        fh.write_file(rel_path, response_text)
        meta_rel = os.path.join(os.path.dirname(rel_path), f"response_{os.path.basename(rel_path)}.meta.json") if os.path.dirname(rel_path) else f"response_{os.path.basename(rel_path)}.meta.json"
        full_meta_path = os.path.join(output_dir, meta_rel)
        os.makedirs(os.path.dirname(full_meta_path) or ".", exist_ok=True)
        # enrich metadata with a timestamp if missing
        if "timestamp" not in metadata:
            metadata["timestamp"] = _now_iso()
        with open(full_meta_path, "w", encoding="utf-8") as mh:
            json.dump(metadata, mh, indent=2)
    except Exception as e:
        LOG.error("Failed to write output files: %s", e)
        return 4

    LOG.info("Wrote response and metadata for %s", rel_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
