#!/usr/bin/env python3
"""Minimal FilePromptForge — OpenAI-only CLI

Synchronous, single-provider CLI that:
- loads prompt files (ordered by CLI or sorted directory listing)
- reads input files from an input directory
- sends system+user prompt to OpenAI via the official Python SDK
- writes responses to output directory as response_<original_filename>

Usage:
  python minimal_cli.py --prompts standard_prompt.txt --input-dir test/input --output-dir test/output

Environment:
  OPENAI_API_KEY must be set in the environment.
"""

import os
import sys
import argparse
import logging
from datetime import datetime
from typing import List
from pathlib import Path
from dotenv import load_dotenv

# Load .env from the filepromptforge directory (script directory)
script_dir = Path(__file__).resolve().parent
dotenv_path = script_dir / ".env"
if dotenv_path.exists():
    load_dotenv(dotenv_path)
else:
    # fallback: attempt to load from default locations (cwd / parent dirs)
    try:
        load_dotenv()
    except Exception:
        pass

try:
    from openai import OpenAI
except Exception as e:
    print("Missing dependency: openai. Install with: pip install -r requirements.txt")
    raise

LOG = None

def setup_logger(verbose: bool=False):
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
            # deterministically sort directory listing
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
        # join using a single newline between prompts (preserve internal newlines)
        return "\n".join(prompts)

class FileHandler:
    def __init__(self, input_dir: str, output_dir: str):
        self.input_dir = input_dir
        self.output_dir = output_dir

    def list_input_files(self) -> List[str]:
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
    def __init__(self, model: str, temperature: float, max_tokens: int):
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY not set in environment. This tool requires a valid OpenAI API key.")
        self.client = OpenAI(api_key=api_key)
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    def send_prompt(self, system_prompt: str, user_prompt: str) -> str:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens
        )
        # Extract content robustly across SDK variants
        content = ""
        try:
            choices = getattr(resp, "choices", []) or []
            if choices:
                c0 = choices[0]
                msg = getattr(c0, "message", None)
                if msg is not None:
                    # message may be an object or a dict
                    if hasattr(msg, "content"):
                        content = msg.content or ""
                    elif isinstance(msg, dict):
                        content = msg.get("content", "") or ""
                if not content and hasattr(c0, "content"):
                    content = getattr(c0, "content") or ""
                if not content and hasattr(c0, "text"):
                    content = getattr(c0, "text") or ""
        except Exception:
            content = ""
        return (content or "").strip()

def main(argv=None):
    parser = argparse.ArgumentParser(description="FilePromptForge - Minimal OpenAI-only CLI")
    parser.add_argument("--prompts", nargs="+", help="Ordered list of prompt filenames (from prompts directory). If omitted, all files in prompts_dir are used in sorted order.")
    parser.add_argument("--prompts-dir", default="test/prompts", help="Directory containing prompt files.")
    parser.add_argument("--input-dir", default="test/input", help="Directory containing input files.")
    parser.add_argument("--output-dir", default="test/output", help="Directory for responses.")
    parser.add_argument("--model", default="gpt-4", help="OpenAI model id to use.")
    parser.add_argument("--temperature", type=float, default=0.7, help="Temperature for the model.")
    parser.add_argument("--max-tokens", type=int, default=1500, help="Max tokens for completion.")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging.")
    args = parser.parse_args(argv)

    setup_logger(args.verbose)
    LOG.info("Starting FilePromptForge (minimal OpenAI-only)")

    pm = PromptManager(args.prompts_dir)
    system_prompt = pm.load_prompts(args.prompts)
    LOG.debug("System prompt loaded (first 500 chars): %s", system_prompt[:500].replace("\n", "\\n"))

    fh = FileHandler(args.input_dir, args.output_dir)
    input_files = fh.list_input_files()
    if not input_files:
        LOG.info("No input files found in %s. Exiting.", args.input_dir)
        return 0

    client = APIClient(args.model, args.temperature, args.max_tokens)

    for idx, rel in enumerate(input_files):
        LOG.info("Processing %s (%d/%d)", rel, idx+1, len(input_files))
        user_prompt = fh.read_file(rel)
        LOG.debug("User prompt length: %d", len(user_prompt))
        response = client.send_prompt(system_prompt, user_prompt)
        fh.write_file(rel, response)
        LOG.info("Wrote response for %s", rel)

    LOG.info("Processing complete.")
    return 0

if __name__ == "__main__":
    sys.exit(main())