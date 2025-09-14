import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import yaml  # type: ignore
except Exception:
    yaml = None  # We will handle absence gracefully

import urllib.request
import urllib.error


DEFAULT_PROVIDER_URL = "https://openrouter.ai/api/v1/chat/completions"


def deep_merge_dicts(d1: Dict[str, Any], d2: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merges d2 into a new dictionary based on d1."""
    merged = d1.copy()
    for k, v in d2.items():
        if k in merged and isinstance(merged[k], dict) and isinstance(v, dict):
            merged[k] = deep_merge_dicts(merged[k], v)
        else:
            merged[k] = v
    return merged


def load_config(config_path: Path) -> Dict[str, Any]:
    file_cfg: Dict[str, Any] = {}
    if config_path.exists() and yaml is not None:
        with config_path.open("r", encoding="utf-8") as f:
            try:
                file_cfg = yaml.safe_load(f) or {}
                print(f"DEBUG: Raw file_cfg from YAML: {json.dumps(file_cfg, indent=2)}")
            except Exception as e:
                print(f"DEBUG: Error loading YAML: {e}")
                pass

    # Build the final config, prioritizing file_cfg values
    cfg: Dict[str, Any] = {
        "provider_url": file_cfg.get("provider_url", DEFAULT_PROVIDER_URL),
        "model": file_cfg.get("model", "openai/gpt-4o-mini:online"),
        "prompt_template": file_cfg.get("prompt_template", (
            "You are File Prompt Forge (FPF). Combine the following two files into a single, helpful response.\n"
            "Crucially, you MUST use web search to find up-to-date information for any questions or topics that require current knowledge.\n"
            "Cite all web search results using markdown links named using the domain of the source. Example: [nytimes.com](https://nytimes.com/some-page).\n\n"
            "# File A ({{file_a_name}})\n{{file_a}}\n\n"
            "# File B ({{file_b_name}})\n{{file_b}}\n\n"
            "# Task\nProvide the best possible answer using both files and the web search results."
        )),
        "web_search": {
            "enable": file_cfg.get("web_search", {}).get("enable", True),
            "max_results": file_cfg.get("web_search", {}).get("max_results", 5),
            "search_prompt": file_cfg.get("web_search", {}).get("search_prompt", "A web search was conducted. Incorporate the following web search results into your response. IMPORTANT: Cite them using markdown links named using the domain of the source. Example: [nytimes.com](https://nytimes.com/some-page)."),
        },
        "referer": file_cfg.get("referer", "https://local.dev/fpf"),
        "title": file_cfg.get("title", "File Prompt Forge"),
    }
    print(f"DEBUG: Final constructed config: {json.dumps(cfg, indent=2)}")
    return cfg


def load_env_files(paths: list[Path], *, overwrite: bool = False) -> None:
    """Minimal .env loader: KEY=VALUE lines, ignores comments and blanks.
    Later files only set variables not already present unless overwrite=True.
    Supports optional leading 'export ' and simple quoted values.
    """
    for p in paths:
        if not p or not p.exists():
            continue
        try:
            for raw in p.read_text(encoding="utf-8", errors="replace").splitlines():
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if line.lower().startswith("export "):
                    line = line[7:].lstrip()
                if "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip()
                if (val.startswith("\"") and val.endswith("\"")) or (
                    val.startswith("'") and val.endswith("'")
                ):
                    val = val[1:-1]
                if overwrite or key not in os.environ:
                    os.environ[key] = val
        except Exception:
            # Fail-soft: ignore unreadable dotenv files
            continue


def compose_input(file_a: Path, file_b: Path, template: str) -> str:
    a_txt = file_a.read_text(encoding="utf-8", errors="replace")
    b_txt = file_b.read_text(encoding="utf-8", errors="replace")
    out = (
        template
        .replace("{{file_a_name}}", file_a.name)
        .replace("{{file_b_name}}", file_b.name)
        .replace("{{file_a}}", a_txt)
        .replace("{{file_b}}", b_txt)
    )
    return out


def _headers(api_key: str, referer: Optional[str], title: Optional[str]) -> Dict[str, str]:
    h = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    # OpenRouter recommends these for identification/analytics
    if referer:
        h["HTTP-Referer"] = referer
    if title:
        h["X-Title"] = title
    return h


def call_openrouter_responses(
    *,
    provider_url: str,
    api_key: str,
    model: str,
    input_text: str,
    web_search: Optional[Dict[str, Any]] = None,
    referer: Optional[str] = None,
    title: Optional[str] = None,
) -> Dict[str, Any]:
    print(f"DEBUG: web_search received in call_openrouter_responses: {json.dumps(web_search, indent=2)}") # New debug print
    payload: Dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": input_text}],
    }
    # Construct the web plugin configuration based on web_search settings
    web_plugin_config: Dict[str, Any] = {"id": "web"}
    if web_search:
        if "max_results" in web_search and web_search["max_results"] is not None:
            web_plugin_config["max_results"] = web_search["max_results"]
        if "search_prompt" in web_search and web_search["search_prompt"] != "":
            web_plugin_config["search_prompt"] = web_search["search_prompt"]
    
    print(f"DEBUG: Web Plugin Config: {json.dumps(web_plugin_config, indent=2)}") # Added debug print
    payload["plugins"] = [web_plugin_config] # Moved this line after populating web_plugin_config
    print(f"DEBUG: OpenRouter API Payload: {json.dumps(payload, indent=2)}")

    req = urllib.request.Request(
        provider_url,
        data=json.dumps(payload).encode("utf-8"),
        headers=_headers(api_key, referer, title),
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:  # nosec: trusted URL configured by user
            raw_bytes = resp.read()
            raw = raw_bytes.decode("utf-8", errors="replace") if raw_bytes else ""
            if not raw.strip():
                raise RuntimeError("OpenRouter returned empty response body")
            try:
                return json.loads(raw)
            except json.JSONDecodeError as je:
                raise RuntimeError(f"OpenRouter returned non-JSON response: {raw[:400]}...") from je
    except urllib.error.HTTPError as he:
        body = he.read().decode("utf-8", errors="replace") if hasattr(he, 'read') else ""
        snippet = (body or str(he))[:600]
        raise RuntimeError(f"HTTP {he.code} from OpenRouter: {snippet}") from he
    except urllib.error.URLError as ue:
        raise RuntimeError(f"Network error calling OpenRouter: {ue}") from ue


def extract_text(resp_json: Dict[str, Any]) -> str:
    # Try OpenAI-like Responses API shape
    if isinstance(resp_json, dict):
        if "output_text" in resp_json and isinstance(resp_json["output_text"], str):
            return resp_json["output_text"].strip()

        # Some providers may return an array under "output" with content blocks
        output = resp_json.get("output")
        if isinstance(output, list) and output:
            # Each item may contain {type, text} or nested content
            parts = []
            for item in output:
                if isinstance(item, dict):
                    txt = item.get("content") or item.get("text")
                    if isinstance(txt, str):
                        parts.append(txt)
                    elif isinstance(txt, list):
                        for sub in txt:
                            if isinstance(sub, dict) and isinstance(sub.get("text"), str):
                                parts.append(sub["text"]) 
            if parts:
                return "\n\n".join(p.strip() for p in parts if p)

        # Fallback for chat-like shapes if Responses proxies them
        choices = resp_json.get("choices")
        if isinstance(choices, list) and choices:
            msg = choices[0].get("message") if isinstance(choices[0], dict) else None
            if isinstance(msg, dict):
                content = msg.get("content")
                if isinstance(content, str):
                    return content.strip()
                if isinstance(content, list):
                    # OpenAI tool/message array content shape
                    texts = [c.get("text") for c in content if isinstance(c, dict) and isinstance(c.get("text"), str)]
                    if texts:
                        return "\n\n".join(t.strip() for t in texts if t)

    # Final fallback: pretty-print entire JSON
    return json.dumps(resp_json, indent=2)


def derive_output_path(file_b: Path, explicit_out: Optional[Path]) -> Path:
    if explicit_out is not None:
        return explicit_out
    # Name after the second file with a conventional suffix
    return file_b.with_name(f"{file_b.name}.fpf.response.txt")


def run(
    file_a: Path,
    file_b: Path,
    *,
    config: Dict[str, Any],
    model: Optional[str] = None,
    out_path: Optional[Path] = None,
    provider_url: Optional[str] = None,
) -> Path:
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY not set. Cannot call OpenRouter.")
    print(f"DEBUG: Using API Key: {api_key[:4]}...{api_key[-4:]}")

    pv_url = provider_url or config.get("provider_url") or DEFAULT_PROVIDER_URL
    mdl = model or config.get("model") or "openai/gpt-4o-mini"
    # Ensure ":online" tag is applied to leverage the web plugin per docs
    mdl_online = mdl if ":online" in str(mdl) else f"{mdl}:online"
    template = config.get("prompt_template") or "{{file_a}}\n\n{{file_b}}"
    web_search = config.get("web_search") or {"enable": True}
    print(f"DEBUG: web_search from config: {web_search}") # Added debug print
    referer = config.get("referer")
    title = config.get("title")

    input_text = compose_input(file_a, file_b, str(template))
    response_json = call_openrouter_responses(
        provider_url=str(pv_url),
        api_key=str(api_key),
        model=str(mdl_online),
        input_text=input_text,
        web_search=web_search,
        referer=referer,
        title=title,
    )
    output_text = extract_text(response_json)

    out_file = derive_output_path(file_b, out_path)
    out_file.write_text(output_text, encoding="utf-8")
    return out_file


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="fileprompt-forge",
        description="FPF: Combine two files into one LLM prompt via OpenRouter Responses API (with web search).",
    )
    p.add_argument("file_a", type=Path, help="First input file path")
    p.add_argument("file_b", type=Path, help="Second input file path")
    p.add_argument("--config", type=Path, default=Path("fpf_config.yaml"), help="Path to YAML config (default: fpf_config.yaml)")
    p.add_argument("--model", type=str, help="Override model from config")
    p.add_argument("--out", type=Path, help="Output file path (default: <file_b>.fpf.response.txt)")
    p.add_argument("--provider-url", type=str, help="Override provider URL (default: OpenRouter Responses)")
    p.add_argument("--env", type=Path, help="Path to a .env file containing OPENROUTER_API_KEY (default searches fpf/.env then .env)")
    return p.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)

    for fp in (args.file_a, args.file_b):
        if not fp.exists():
            print(f"Error: file not found: {fp}", file=sys.stderr)
            return 2

    # Load API key from .env if present
    env_paths: list[Path] = []
    if args.env:
        env_paths.append(args.env)
    else:
        env_paths.extend([Path("fpf/.env"), Path(".env")])
    load_env_files(env_paths, overwrite=False)

    cfg = load_config(args.config)
    try:
        out_file = run(
            args.file_a,
            args.file_b,
            config=cfg,
            model=args.model,
            out_path=args.out,
            provider_url=args.provider_url,
        )
    except Exception as e:
        print(f"FPF error: {e}", file=sys.stderr)
        return 1

    print(str(out_file))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
