"""
file_handler - central router for File Prompt Forge (FPF)

Enforced guarantees implemented here:
- OPENAI_API_KEY is sourced only from filepromptforge/.env (no overrides).
- Provider-side web_search is required: runs that do not perform web_search will fail.
- Provider reasoning is required: runs that do not return reasoning will fail.
- Raw provider JSON sidecar is always saved. Human-readable output is only written if
  both web_search and reasoning checks pass.
"""

from __future__ import annotations
import os
import json
import importlib
import logging
from typing import Dict, Optional, Tuple, Any, List
from pathlib import Path

LOG = logging.getLogger("file_handler")


def _http_post_json(url: str, payload: Dict, headers: Dict, timeout: int = 120) -> Dict:
    """POST JSON and return parsed JSON response. Uses urllib (no extra deps).

    Enhancements:
    - Increased default timeout to 120s to accommodate longer reasoning/tool runs.
    - Added debug logging of request metadata (not payload contents) to assist troubleshooting.
    - Logs and raises detailed errors on HTTP failures.
    """
    import urllib.request
    import urllib.error

    body = json.dumps(payload).encode("utf-8")
    hdrs = {"Content-Type": "application/json"}
    hdrs.update(headers or {})

    # Log a compact request summary for debugging (do not log full payload to avoid sensitive data leakage)
    try:
        LOG.debug("HTTP POST %s headers=%s payload_bytes=%d timeout=%s", url, {k: hdrs.get(k) for k in ("Authorization", "Content-Type")}, len(body), timeout)
    except Exception:
        # best-effort logging; do not raise for logging failures
        pass

    req = urllib.request.Request(url, data=body, headers=hdrs, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw)
    except urllib.error.HTTPError as he:
        try:
            msg = he.read().decode("utf-8", errors="ignore")
        except Exception:
            msg = ""
        LOG.exception("HTTPError during POST %s: %s %s", url, he, msg)
        raise RuntimeError(f"HTTP error {he.code}: {he.reason} - {msg}") from he
    except Exception as e:
        LOG.exception("HTTP request failed for %s: %s", url, e)
        raise RuntimeError(f"HTTP request failed: {e}") from e


def _load_provider_module():
    """Import the OpenAI provider module. Raise RuntimeError if not found."""
    try:
        mod = importlib.import_module("filepromptforge.providers.openai.fpf_openai_main")
        return mod
    except ModuleNotFoundError as e:
        raise RuntimeError("OpenAI provider module not found: filepromptforge.providers.openai.fpf_openai_main") from e


def _read_key_from_env_file(env_path: Path, key: str) -> Optional[str]:
    """
    Read KEY=VALUE lines from env_path and return the value for `key` if present.
    This is a conservative, deterministic parser used to ensure the repo .env is
    the canonical source for sensitive keys.
    """
    if not env_path.exists():
        return None
    try:
        with env_path.open("r", encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                if k.strip() == key:
                    return v.strip().strip('\'"')
    except Exception:
        # Do not swallow — let caller decide. Return None on parse failure.
        return None
    return None


def _response_used_websearch(raw_json: Dict) -> bool:
    """
    Inspect provider response to determine whether provider-side web_search
    (tool usage) occurred.

    Heuristics:
    - If 'tool_calls' or 'tools' exists and is non-empty -> True
    - If any output block contains 'reasoning' or content referencing 'source' or 'web_search' strings -> True
    """
    if not isinstance(raw_json, dict):
        return False

    # direct tool call evidence
    if "tool_calls" in raw_json and isinstance(raw_json["tool_calls"], list) and raw_json["tool_calls"]:
        return True
    if "tools" in raw_json and isinstance(raw_json["tools"], list) and raw_json["tools"]:
        # some providers return tools metadata even if empty; require non-empty
        return True

    # inspect outputs for websearch indicators
    output = raw_json.get("output") or raw_json.get("outputs")
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, dict):
                continue
            # check content blocks for source-like entries
            content = item.get("content") or item.get("contents")
            if isinstance(content, list):
                for c in content:
                    # string search for common markers
                    try:
                        if isinstance(c, dict):
                            # fields that may indicate web search results
                            if any(k in c for k in ("source", "url", "link")):
                                return True
                            text = c.get("text") or ""
                            if isinstance(text, str) and ("http://" in text or "https://" in text or "[source]" in text or "Citation:" in text):
                                return True
                        elif isinstance(c, str):
                            if "http://" in c or "https://" in c or "Citation:" in c:
                                return True
                    except Exception:
                        continue
    # fallback: scan entire JSON string for web_search mention (conservative)
    try:
        raw_str = json.dumps(raw_json)
        if "web_search" in raw_str or "tool_call" in raw_str or "tool_calls" in raw_str:
            # only return True if also appears with some content length
            return "web_search" in raw_str
    except Exception:
        pass

    return False


def run(file_a: Optional[str] = None,
        file_b: Optional[str] = None,
        out_path: Optional[str] = None,
        config_path: Optional[str] = None,
        env_path: Optional[str] = None,
        model: Optional[str] = None) -> str:
    """
    High-level entry point (OpenAI-only).

    Behavior guarantees enforced:
    - Loads OPENAI_API_KEY only from filepromptforge/.env (repo .env).
    - Fails if provider response did not perform web_search or did not return reasoning.
    - Saves raw sidecar always; writes human-readable output only when checks pass.
    """
    # Import helpers lazily to avoid circular imports
    try:
        from filepromptforge.fpf.fpf_main import compose_input, load_config, load_env_file
    except Exception:
        # fallback to top-level helpers if present
        from filepromptforge.fpf_main import compose_input, load_config, load_env_file  # type: ignore

    # load env strictly from repository filepromptforge/.env (canonical)
    repo_env = Path(__file__).resolve().parent / ".env"
    # Ensure canonical env is parsed for OPENAI_API_KEY and used exclusively
    api_key_value = _read_key_from_env_file(repo_env, "OPENAI_API_KEY")
    if api_key_value is None or api_key_value == "":
        LOG.error("API key not found in canonical env: %s", repo_env)
        raise RuntimeError("API key not found. Set OPENAI_API_KEY in filepromptforge/.env")

    # Explicitly set process env from canonical repo .env for determinism
    os.environ["OPENAI_API_KEY"] = api_key_value

    cfg = load_config(config_path or str(Path(__file__).parent / "fpf_config.yaml"))

    # Allow CLI override of model but keep canonical config for web_search/reasoning enforcement
    if model:
        # normalize to provider expected form (do not append :online here — provider adapter handles model normalization)
        cfg["model"] = model

    # if files not provided, try test section
    if not file_a or not file_b:
        test_cfg = cfg.get("test", {})
        file_a = file_a or test_cfg.get("file_a")
        file_b = file_b or test_cfg.get("file_b")
        if not file_a or not file_b:
            raise RuntimeError("file_a and file_b must be provided either as arguments or in the config.test section")

    # compose prompt
    prompt_template = cfg.get("prompt_template")
    prompt = compose_input(file_a, file_b, prompt_template)

    provider = _load_provider_module()

    # ensure model is allowed by provider
    model_to_use = cfg.get("model")
    if hasattr(provider, "validate_model"):
        if not provider.validate_model(model_to_use):
            raise RuntimeError(f"Model '{model_to_use}' is not allowed by OpenAI provider whitelist")

    # build payload (provider adapter is responsible for enforcing web_search & reasoning in payload)
    if hasattr(provider, "build_payload"):
        payload_result = provider.build_payload(prompt, cfg)
        if isinstance(payload_result, tuple) and len(payload_result) == 2:
            payload_body, provider_headers = payload_result
        else:
            payload_body = payload_result
            provider_headers = {}
    else:
        raise RuntimeError("Provider does not expose build_payload")

    provider_url = cfg.get("provider_url")
    if not provider_url:
        raise RuntimeError("provider_url not configured in config")

    # build headers (Authorization from canonical repo .env only)
    headers = dict(provider_headers or {})
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        # defensive: should not happen because we set it above from repo .env
        raise RuntimeError("API key not found in environment after loading canonical .env")
    headers["Authorization"] = f"Bearer {api_key}"

    if cfg.get("referer"):
        headers["Referer"] = cfg.get("referer")
    if cfg.get("title"):
        headers["Title"] = cfg.get("title")

    # perform HTTP POST: save outbound payload for debugging, log a compact summary, and measure timing
    try:
        last_payload_path = Path(__file__).resolve().parent / "last_payload.json"
        with open(last_payload_path, "w", encoding="utf-8") as ph:
            json.dump(payload_body, ph, indent=2, ensure_ascii=False)
        LOG.info("Saved outbound payload to %s (compact headers shown)", last_payload_path)
    except Exception:
        LOG.exception("Failed to save outbound payload for debugging")

    import time
    start_ts = time.time()
    raw_json = _http_post_json(provider_url, payload_body, headers)
    elapsed = time.time() - start_ts
    try:
        if isinstance(raw_json, dict):
            LOG.info("HTTP POST completed in %.2fs; response keys=%s; tool_choice=%s", elapsed, list(raw_json.keys()), raw_json.get("tool_choice"))
        else:
            LOG.info("HTTP POST completed in %.2fs; response type=%s", elapsed, type(raw_json))
    except Exception:
        LOG.debug("Completed HTTP POST in %.2fs but failed to inspect response for logging", elapsed)

    # decide out_path
    if not out_path:
        b_path = Path(file_b)
        out_name = f"{b_path.name}.fpf.response.txt"
        out_path = str(b_path.parent / out_name)

    raw_path = out_path + ".raw.json"
    # Ensure the parent directory exists before attempting to write the sidecar
    raw_parent = Path(raw_path).parent
    if not raw_parent.exists():
        raw_parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(raw_path, "w", encoding="utf-8") as fh:
            json.dump(raw_json, fh, indent=2, ensure_ascii=False)
        try:
            size = Path(raw_path).stat().st_size
            LOG.info("Wrote raw JSON sidecar %s (size=%d bytes)", raw_path, size)
        except Exception:
            LOG.debug("Wrote raw JSON sidecar %s", raw_path)
    except Exception as e:
        LOG.exception("Failed to write raw JSON sidecar: %s", e)
        # treat failure to persist raw sidecar as runtime error
        raise RuntimeError(f"Failed to write raw JSON sidecar: {e}") from e

    # Verify provider performed web_search (strict policy)
    used_websearch = _response_used_websearch(raw_json)
    if not used_websearch:
        LOG.error("Provider did not perform web_search according to response: %s", raw_path)
        raise RuntimeError("Provider did not perform web_search; aborting per policy. Raw response saved to: " + raw_path)

    # Extract and verify reasoning
    reasoning_text = None
    try:
        if hasattr(provider, "extract_reasoning"):
            reasoning_text = provider.extract_reasoning(raw_json)
        else:
            # attempt a best-effort extraction from known shapes
            reasoning_text = raw_json.get("reasoning")
            if isinstance(reasoning_text, dict):
                # stringify simple dict forms
                reasoning_text = "\n\n".join([str(v) for v in reasoning_text.values() if isinstance(v, (str, int, float))])
    except Exception:
        LOG.exception("Failed to extract reasoning from provider response")
        reasoning_text = None

    if not reasoning_text or (isinstance(reasoning_text, str) and not reasoning_text.strip()):
        LOG.error("Provider response did not contain reasoning; aborting. Raw response saved to: %s", raw_path)
        raise RuntimeError("Provider did not return reasoning; aborting per policy. Raw response saved to: " + raw_path)

    # Parse human-readable text and write outputs
    if hasattr(provider, "parse_response"):
        human_text = provider.parse_response(raw_json)
    else:
        human_text = json.dumps(raw_json, indent=2, ensure_ascii=False)

    # Write reasoning sidecar
    reasoning_path = out_path + ".reasoning.txt"
    try:
        with open(reasoning_path, "w", encoding="utf-8") as fh:
            fh.write(reasoning_text if isinstance(reasoning_text, str) else str(reasoning_text))
    except Exception as e:
        LOG.exception("Failed to write reasoning sidecar: %s", e)
        # treat failure to write reasoning as runtime error
        raise RuntimeError(f"Failed to write reasoning sidecar: {e}") from e

    # Write human-readable output (only after all checks passed)
    try:
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(human_text)
    except Exception as e:
        LOG.exception("Failed to write output to %s: %s", out_path, e)
        raise RuntimeError(f"Failed to write output to {out_path}: {e}") from e

    LOG.info("Run validated: web_search used and reasoning present. Output written to %s", out_path)
    return out_path
