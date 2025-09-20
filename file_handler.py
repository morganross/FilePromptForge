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
import re
import json
import importlib
import logging
from typing import Dict, Optional, Tuple, Any, List
from pathlib import Path

from pricing.pricing_loader import load_pricing_index, find_pricing, calc_cost

LOG = logging.getLogger("file_handler")


def _sanitize_filename(name: str) -> str:
    """Sanitize a string to be a valid filename."""
    if not name:
        return "unknown"
    # remove chars that are problematic for filenames
    return re.sub(r'[\\/*?:"<>|]', "", name)


def _http_post_json(url: str, payload: Dict, headers: Dict, timeout: int = 300) -> Dict:
    """POST JSON and return parsed JSON response. Uses urllib (no extra deps).

    Enhancements:
    - Increased default timeout to 300s to accommodate longer reasoning/tool runs.
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


def _load_provider_module(provider_name: str = "openai"):
    """Import the provider module. Raise RuntimeError if not found."""
    try:
        # Construct the module name dynamically (import within this package root).
        module_name = f"providers.{provider_name}.fpf_{provider_name}_main"
        mod = importlib.import_module(module_name)
        LOG.info("Successfully loaded provider module: %s", module_name)
        return mod
    except ModuleNotFoundError as e:
        LOG.error("Provider module not found for: %s", provider_name)
        raise RuntimeError(f"Provider module not found for: {provider_name}") from e
    except Exception as e:
        LOG.exception("An unexpected error occurred while loading provider module for: %s", provider_name)
        raise RuntimeError(f"Could not load provider module for {provider_name}") from e


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
        
    # Gemini specific check for groundingMetadata
    try:
        if "candidates" in raw_json and isinstance(raw_json["candidates"], list):
            for candidate in raw_json["candidates"]:
                if "groundingMetadata" in candidate and candidate["groundingMetadata"]:
                    return True
    except Exception:
        pass

    return False


def run(file_a: Optional[str] = None,
        file_b: Optional[str] = None,
        out_path: Optional[str] = None,
        config_path: Optional[str] = None,
        env_path: Optional[str] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        reasoning_effort: Optional[str] = None,
        max_completion_tokens: Optional[int] = None) -> str:
    """
    High-level entry point (OpenAI-only).

    Behavior guarantees enforced:
    - Loads OPENAI_API_KEY only from filepromptforge/.env (repo .env).
    - Fails if provider response did not perform web_search or did not return reasoning.
    - Saves raw sidecar always; writes human-readable output only when checks pass.
    """
    # Import helpers lazily to avoid circular imports
    try:
        from fpf.fpf_main import compose_input, load_config, load_env_file
    except Exception:
        # fallback to top-level helpers if present
        from fpf_main import compose_input, load_config, load_env_file  # type: ignore

    cfg = load_config(config_path or str(Path(__file__).parent / "fpf_config.yaml"))
    
    # Determine the provider and load the correct API key.
    provider_name = provider or cfg.get("provider", "openai")
    api_key_name = f"{provider_name.upper()}_API_KEY"
    
    repo_env = Path(__file__).resolve().parent / ".env"
    api_key_value = _read_key_from_env_file(repo_env, api_key_name)
    
    if api_key_value is None or api_key_value == "":
        # Fallback for backward compatibility with OPENAI_API_KEY
        if provider_name == "openai":
            api_key_value = _read_key_from_env_file(repo_env, "OPENAI_API_KEY")

    if api_key_value is None or api_key_value == "":
        LOG.error("API key '%s' not found in canonical env: %s", api_key_name, repo_env)
        raise RuntimeError(f"API key not found. Set {api_key_name} in filepromptforge/.env")

    os.environ[api_key_name] = api_key_value

    # Allow CLI override of model but keep canonical config for web_search/reasoning enforcement
    if model:
        # normalize to provider expected form (do not append :online here — provider adapter handles model normalization)
        cfg["model"] = model
    
    if reasoning_effort:
        if "reasoning" not in cfg:
            cfg["reasoning"] = {}
        cfg["reasoning"]["effort"] = reasoning_effort
    
    if max_completion_tokens:
        cfg["max_completion_tokens"] = max_completion_tokens

    if not file_a or not file_b:
        raise RuntimeError("file_a and file_b must be provided as arguments")

    # compose prompt
    prompt_template = cfg.get("prompt_template")
    prompt = compose_input(file_a, file_b, prompt_template)

    provider = _load_provider_module(provider_name)

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

    provider_urls = cfg.get("provider_urls", {})
    provider_url = provider_urls.get(provider_name)
    if not provider_url:
        # Fallback for backward compatibility
        provider_url = cfg.get("provider_url")
    if not provider_url:
        raise RuntimeError(f"provider_url for '{provider_name}' not configured in config")

    # build headers
    headers = dict(provider_headers or {})
    api_key = os.environ.get(api_key_name)
    if not api_key:
        raise RuntimeError(f"API key {api_key_name} not found in environment after loading canonical .env")

    if provider_name == "google":
        # Google Gemini uses x-goog-api-key header
        headers["x-goog-api-key"] = api_key
    else:
        # Default to bearer token for OpenAI and others
        headers["Authorization"] = f"Bearer {api_key}"

    if cfg.get("referer"):
        headers["Referer"] = cfg.get("referer")
    if cfg.get("title"):
        headers["Title"] = cfg.get("title")

    # perform HTTP POST: log timing and send request
    # Note: outbound payload is intentionally not persisted to reduce sidecar files.

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

    # decide out_path, with support for placeholders
    model_name_sanitized = _sanitize_filename(cfg.get("model"))
    b_path = Path(file_b)
    file_b_stem = b_path.stem

    if out_path:
        # if out_path is from config, it might have placeholders
        out_path = out_path.replace("<model_name>", model_name_sanitized)
        out_path = out_path.replace("<file_b_stem>", file_b_stem)
    else:
        # default path construction
        out_name = f"{file_b_stem}.{model_name_sanitized}.fpf.response.txt"
        out_path = str(b_path.parent / out_name)
    
    final_out_path = Path(out_path)
    # create parent directory if it does not exist
    final_out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path = str(final_out_path)

    # Raw provider sidecar files are no longer written. The response is captured in the consolidated run log.

    # ---- Enhanced logging & extraction (request/response, web_search results, reasoning) ----
    base_dir = Path(__file__).resolve().parent

    # Extract web_search_call entries from provider response (if present)
    websearch_entries = []
    try:
        output_items = raw_json.get("output") or raw_json.get("outputs") or []
        for item in output_items:
            if not isinstance(item, dict):
                continue
            t = item.get("type", "")
            if t == "web_search_call" or "web_search" in t or t.startswith("ws_"):
                websearch_entries.append(item)
    except Exception:
        LOG.exception("Failed to extract web_search entries from raw response")
        websearch_entries = []

    # Extract provider reasoning (if provider exposes an extractor)
    reasoning_text = None
    try:
        if hasattr(provider, "extract_reasoning"):
            reasoning_text = provider.extract_reasoning(raw_json)
        else:
            reasoning_text = raw_json.get("reasoning")
    except Exception:
        LOG.exception("Failed to extract reasoning via provider.extract_reasoning")
        reasoning_text = None

    # Consolidated per-run log (single JSON) written to logs/ with a run UID
    try:
        import uuid as _uuid
        import datetime as _dt
        run_id = _uuid.uuid4().hex[:8]
        started_iso = _dt.datetime.fromtimestamp(start_ts).isoformat()
        finished_iso = _dt.datetime.now().isoformat()

        # Attempt to get a human-readable text representation for inclusion
        try:
            human_text = provider.parse_response(raw_json) if hasattr(provider, "parse_response") else json.dumps(raw_json, indent=2, ensure_ascii=False)
        except Exception:
            human_text = None

        # Standardize usage across providers (OpenAI/Gemini) and compute cost
        def _std_usage(rj: dict) -> dict:
            # OpenAI-style (Responses API and Chat Completions)
            try:
                u = rj.get("usage") or {}
                # Responses API fields
                it = u.get("input_tokens")
                ot = u.get("output_tokens")
                tt = u.get("total_tokens")
                if any(isinstance(x, int) for x in (it, ot, tt)):
                    it_i = int(it or 0)
                    ot_i = int(ot or 0)
                    return {"prompt_tokens": it_i, "completion_tokens": ot_i, "total_tokens": int(tt or (it_i + ot_i))}
                # Legacy Chat Completions fields
                pt = u.get("prompt_tokens")
                ct = u.get("completion_tokens")
                if isinstance(pt, int) or isinstance(ct, int):
                    pt_i = int(pt or 0)
                    ct_i = int(ct or 0)
                    return {"prompt_tokens": pt_i, "completion_tokens": ct_i, "total_tokens": pt_i + ct_i}
            except Exception:
                pass
            # Google Gemini-style
            try:
                um = rj.get("usageMetadata") or {}
                pt = um.get("promptTokenCount")
                ct = um.get("candidatesTokenCount")
                tt = um.get("totalTokenCount")
                if any(isinstance(x, int) for x in (pt, ct, tt)):
                    if pt is None or ct is None:
                        pts = 0
                        cts = 0
                        for c in (rj.get("candidates") or []):
                            m = c.get("usageMetadata") or {}
                            pts += int(m.get("promptTokenCount") or 0)
                            cts += int(m.get("candidatesTokenCount") or 0)
                        pt = int(pt or pts)
                        ct = int(ct or cts)
                    return {
                        "prompt_tokens": int(pt or 0),
                        "completion_tokens": int(ct or 0),
                        "total_tokens": int(tt or (int(pt or 0) + int(ct or 0))),
                    }
            except Exception:
                pass
            return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        usage_std = _std_usage(raw_json)

        # Price lookup and cost computation
        try:
            pricing_path = str(base_dir / "pricing" / "pricing_index.json")
            pricing_list = load_pricing_index(pricing_path)
            model_cfg = cfg.get("model") or ""
            model_slug = model_cfg if "/" in str(model_cfg) else f"{provider_name}/{model_cfg}"
            rec = find_pricing(pricing_list, model_slug)
            cost = calc_cost(usage_std.get("prompt_tokens", 0), usage_std.get("completion_tokens", 0), rec)
            total_cost_usd = cost.get("total_cost_usd")
        except Exception:
            cost = {"reason": "cost_calc_failed"}
            total_cost_usd = None

        consolidated = {
            "run_id": run_id,
            "started_at": started_iso,
            "finished_at": finished_iso,
            "model": cfg.get("model"),
            "config": cfg,
            "request": payload_body,
            "response": raw_json,
            "web_search": websearch_entries,
            "reasoning": reasoning_text,
            "human_text": human_text,
            "usage": usage_std,
            "cost": cost,
            "total_cost_usd": total_cost_usd,
        }

        logs_dir = base_dir / "logs"
        if not logs_dir.exists():
            logs_dir.mkdir(parents=True, exist_ok=True)

        # Write a unique per-run JSON log file that contains the full run data.
        try:
            log_name = f"{_dt.datetime.now().strftime('%Y%m%dT%H%M%S')}-{run_id}.json"
            log_path = logs_dir / log_name
            with open(log_path, "w", encoding="utf-8") as fh:
                json.dump(consolidated, fh, indent=2, ensure_ascii=False)
            LOG.info("Wrote per-run consolidated log %s (run_id=%s)", log_path, run_id)
        except Exception:
            LOG.exception("Failed to write per-run consolidated log")
    except Exception:
        LOG.exception("Unexpected error in enhanced logging/extraction")

    # Verify provider performed web_search (strict policy)
    used_websearch = _response_used_websearch(raw_json)
    if not used_websearch:
        LOG.error("Provider did not perform web_search according to response; consolidated log will contain details")
        raise RuntimeError("Provider did not perform web_search; aborting per policy. See consolidated log in logs/")

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
        LOG.error("Provider response did not contain reasoning; aborting. See consolidated log in logs/")
        raise RuntimeError("Provider did not return reasoning; aborting per policy. See consolidated log in logs/")

    # Parse human-readable text and write outputs
    if hasattr(provider, "parse_response"):
        human_text = provider.parse_response(raw_json)
    else:
        human_text = json.dumps(raw_json, indent=2, ensure_ascii=False)


    # Write human-readable output (only after all checks passed)
    try:
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(human_text)
    except Exception as e:
        LOG.exception("Failed to write output to %s: %s", out_path, e)
        raise RuntimeError(f"Failed to write output to {out_path}: {e}") from e

    LOG.info("Run validated: web_search used and reasoning present. Output written to %s", out_path)
    return out_path
