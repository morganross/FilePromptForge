"""
CodexExecAPI provider adapter for FPF.

This provider is OpenAI-compatible on the wire, but it routes to the private
CodexExecAPI facade instead of the public OpenAI API. It preserves FPF's strict
invariants by returning Codex-derived web-search and reasoning proof in a shape
that grounding_enforcer already understands.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple
import json
import logging
import os
import random
import sys
import time
import urllib.error
import urllib.request

LOG = logging.getLogger("fpf_codexexecapi_main")

REQUIRES_GROUNDING = True
REQUIRES_REASONING = True
SUPPORTED_MODELS = {
    "gpt-5.6-sol",
    "gpt-5.6-terra",
    "gpt-5.6-luna",
    "gpt-5.5",
    "gpt-5.4",
    "gpt-5.4-mini",
}


def _normalize_model(model: str) -> str:
    raw = str(model or "").strip()
    if raw.startswith("codexexecapi:"):
        raw = raw.split(":", 1)[1].strip()
    if not raw:
        raise RuntimeError("CodexExecAPI provider requires a model - no fallback defaults allowed")
    if raw not in SUPPORTED_MODELS:
        raise RuntimeError(
            f"CodexExecAPI model '{raw}' is not supported. "
            f"Supported models: {', '.join(sorted(SUPPORTED_MODELS))}"
        )
    return raw


def _resolve_provider_url(provider_url: str) -> str:
    base = str(os.getenv("CODEX_EXEC_API_URL") or "").strip().rstrip("/")
    if base:
        if base.endswith("/v1/chat/completions"):
            return base
        if base.endswith("/v1"):
            return base + "/chat/completions"
        return base + "/v1/chat/completions"
    if provider_url:
        return provider_url
    raise RuntimeError("CODEX_EXEC_API_URL is required for CodexExecAPI provider")


def _extract_bearer_token(headers: Optional[Dict[str, Any]]) -> str:
    auth = str((headers or {}).get("Authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
        if token:
            return token
    token = str(os.getenv("CODEX_EXEC_API_TOKEN") or os.getenv("CODEXEXECAPI_API_KEY") or "").strip()
    if token:
        return token
    raise RuntimeError("CODEX_EXEC_API_TOKEN is required for CodexExecAPI provider")


def _is_transient_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(
        token in msg
        for token in (
            "429",
            "rate limit",
            "timeout",
            "timed out",
            "502",
            "503",
            "504",
            "connection",
            "network",
        )
    )


def build_payload(prompt: str, cfg: Dict[str, Any]) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
    model_to_use = _normalize_model(str(cfg.get("model") or ""))
    request_json = bool(cfg.get("json")) if cfg.get("json") is not None else (bool(cfg.get("json_output")) if cfg.get("json_output") is not None else False)
    final_prompt = prompt
    if request_json:
        final_prompt = (
            "Return only a single valid JSON object. "
            "Do not include prose or Markdown fences.\n\n"
            + prompt
        )

    reasoning_effort = (
        (cfg.get("reasoning") or {}).get("effort")
        or cfg.get("reasoning_effort")
        or "medium"
    )
    web_search_cfg = cfg.get("web_search") if isinstance(cfg.get("web_search"), dict) else {}
    search_context_size = (
        web_search_cfg.get("search_context_size")
        or cfg.get("search_context_size")
        or "high"
    )

    payload: Dict[str, Any] = {
        "model": model_to_use,
        "messages": [{"role": "user", "content": final_prompt}],
        "stream": False,
        "tools": [{"type": "web_search"}],
        "tool_choice": "auto",
        "reasoning_effort": reasoning_effort,
        "reasoning": {"effort": reasoning_effort},
        "codexexec": {
            "require_grounding": True,
            "require_reasoning": True,
            "grounding_mode": "web_search",
            "reasoning_effort": reasoning_effort,
            "search_context_size": search_context_size,
        },
    }
    if cfg.get("max_completion_tokens") is not None:
        payload["max_tokens"] = int(cfg["max_completion_tokens"])
    if cfg.get("temperature") is not None:
        payload["temperature"] = float(cfg["temperature"])
    return payload, None


def _normalize_response(raw_json: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(raw_json, dict):
        raise RuntimeError("CodexExecAPI returned non-object JSON")
    content = parse_response(raw_json)
    raw_json.setdefault("output_text", content)

    validation = raw_json.get("codexexec_validation")
    validation = validation if isinstance(validation, dict) else {}

    usage = raw_json.get("usage")
    if not isinstance(usage, dict):
        usage = {}
        raw_json["usage"] = usage

    # Some API responses include usage in alternate fields during rollout.
    # Keep a conservative fallback search so we can still surface token data
    # instead of dropping to all-zero meters.
    for alias in ("usage_tokens", "raw_usage", "usage_stats"):
        _alt = raw_json.get(alias)
        if isinstance(_alt, dict) and any(
            v is not None and str(v).strip() for v in _alt.values()
        ):
            usage = _alt
            raw_json["usage"] = usage
            break

    details = usage.get("output_tokens_details")
    if not isinstance(details, dict):
        details = {}
        usage["output_tokens_details"] = details
    completion_details = usage.get("completion_tokens_details")
    if not isinstance(completion_details, dict):
        completion_details = {}
        usage["completion_tokens_details"] = completion_details

    def _to_int(value: Any) -> int:
        try:
            return int(value)
        except Exception:
            return 0

    reasoning_tokens = max(
        _to_int(usage.get("reasoning_tokens")),
        _to_int(details.get("reasoning_tokens")),
        _to_int(completion_details.get("reasoning_tokens")),
        _to_int(validation.get("reasoning_output_tokens")),
        0,
    )
    usage["reasoning_tokens"] = reasoning_tokens
    details["reasoning_tokens"] = reasoning_tokens
    completion_details["reasoning_tokens"] = reasoning_tokens

    usage["prompt_tokens"] = _to_int(usage.get("prompt_tokens")) or _to_int(usage.get("input_tokens"))
    usage["completion_tokens"] = _to_int(usage.get("completion_tokens")) or _to_int(usage.get("output_tokens"))

    if (_to_int(usage.get("input_tokens")) <= 0 and _to_int(usage.get("output_tokens")) <= 0 and _to_int(usage.get("total_tokens")) <= 0 and reasoning_tokens > 0):
        usage["output_tokens"] = reasoning_tokens
        usage["total_tokens"] = reasoning_tokens

    usage["input_tokens"] = _to_int(usage.get("input_tokens"))
    usage["output_tokens"] = _to_int(usage.get("output_tokens"))
    usage["total_tokens"] = max(
        _to_int(usage.get("total_tokens")),
        _to_int(usage.get("input_tokens")) + _to_int(usage.get("output_tokens")),
    )

    output = raw_json.get("output")
    if not isinstance(output, list):
        output = []
        raw_json["output"] = output

    has_web_search_call = any(
        isinstance(item, dict) and item.get("type") == "web_search_call"
        for item in output
    )
    if validation.get("web_search_queries") and not has_web_search_call:
        for query in validation.get("web_search_queries") or []:
            output.insert(0, {"type": "web_search_call", "action": {"type": "search", "query": str(query)}})
    if not any(isinstance(item, dict) and item.get("type") == "message" for item in output):
        output.append({"type": "message", "content": [{"type": "output_text", "text": content}]})
    if "tool_calls" not in raw_json:
        raw_json["tool_calls"] = [
            item for item in output
            if isinstance(item, dict) and item.get("type") == "web_search_call"
        ]
    return raw_json


def execute_and_verify(
    provider_url: str,
    payload: Dict[str, Any],
    headers: Optional[Dict[str, Any]],
    verify_helpers,
    timeout: Optional[int] = None,
    max_retries: int = 3,
    retry_delay: float = 1.0,
) -> Dict[str, Any]:
    url = _resolve_provider_url(provider_url)
    token = _extract_bearer_token(headers)
    body = json.dumps(payload).encode("utf-8")
    hdrs = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
    last_error: Optional[Exception] = None
    base_delay_ms = int(retry_delay * 1000)
    max_delay_ms = 30000

    for attempt in range(1, max_retries + 1):
        try:
            LOG.info("CodexExecAPI request attempt %d/%d to %s", attempt, max_retries, url)
            req = urllib.request.Request(url, data=body, headers=hdrs, method="POST")
            if timeout is None:
                resp_ctx = urllib.request.urlopen(req)
            else:
                resp_ctx = urllib.request.urlopen(req, timeout=timeout)
            with resp_ctx as resp:
                raw = resp.read().decode("utf-8")
                raw_json = json.loads(raw)
            normalized = _normalize_response(raw_json)
            verify_helpers.assert_grounding_and_reasoning(normalized, provider=sys.modules[__name__])
            return normalized
        except urllib.error.HTTPError as he:
            try:
                msg = he.read().decode("utf-8", errors="ignore")
            except Exception:
                msg = ""
            last_error = RuntimeError(f"HTTP error {getattr(he, 'code', '?')}: {getattr(he, 'reason', '?')} - {msg}")
        except Exception as exc:
            last_error = exc

        if attempt < max_retries and last_error is not None and _is_transient_error(last_error):
            delay_ms = min(base_delay_ms * (2 ** (attempt - 1)), max_delay_ms)
            time.sleep(random.uniform(0, delay_ms) / 1000.0)
            continue
        if last_error is not None:
            raise RuntimeError(f"CodexExecAPI request failed: {last_error}") from last_error

    raise RuntimeError("CodexExecAPI request failed after all retries")


def parse_response(raw_json: Dict[str, Any]) -> str:
    if not isinstance(raw_json, dict):
        return str(raw_json)
    if isinstance(raw_json.get("output_text"), str):
        return raw_json["output_text"]
    choices = raw_json.get("choices")
    if isinstance(choices, list):
        for choice in choices:
            if not isinstance(choice, dict):
                continue
            message = choice.get("message")
            if isinstance(message, dict) and isinstance(message.get("content"), str):
                return message["content"]
    return json.dumps(raw_json, indent=2, ensure_ascii=False)


def extract_reasoning(raw_json: Dict[str, Any]) -> Optional[str]:
    if not isinstance(raw_json, dict):
        return None
    usage = raw_json.get("usage") if isinstance(raw_json.get("usage"), dict) else {}
    details = usage.get("output_tokens_details") if isinstance(usage.get("output_tokens_details"), dict) else {}
    completion_details = usage.get("completion_tokens_details") if isinstance(usage.get("completion_tokens_details"), dict) else {}
    validation = raw_json.get("codexexec_validation") if isinstance(raw_json.get("codexexec_validation"), dict) else {}
    try:
        tokens = max(
            int(usage.get("reasoning_tokens") or 0),
            int(details.get("reasoning_tokens") or 0),
            int(completion_details.get("reasoning_tokens") or 0),
            int(validation.get("reasoning_output_tokens") or 0),
            int(validation.get("reasoning_present") or 0),
        )
    except Exception:
        tokens = 0
    if tokens > 0:
        return f"CodexExec reasoning proof: reasoning_output_tokens={tokens}"
    return None
