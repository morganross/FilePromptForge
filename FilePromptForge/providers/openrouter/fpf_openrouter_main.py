"""
OpenRouter provider adapter for FPF.

Guarantees (non-configurable):
- Server-side web search is always requested via ``openrouter:web_search``.
- Reasoning is always enabled.
- Requests fail fast at runtime if the selected model lacks tools or reasoning
  support in OpenRouter model metadata.
- Responses are accepted only when grounding and reasoning can be proven.
"""

from __future__ import annotations
from typing import Dict, Tuple, Optional, Any, List
import sys
import json
import copy
import logging
import random
import time
import threading
import urllib.request
import urllib.error
from pathlib import Path

LOG = logging.getLogger("fpf_openrouter_main")

# Provider-level flags: OpenRouter is a strict research path in FPF.
REQUIRES_GROUNDING = True
REQUIRES_REASONING = True

# OpenRouter uses OpenAI-compatible API
DEFAULT_API_BASE = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODELS_API_BASE = "https://openrouter.ai/api/v1"

# Allow all models - OpenRouter handles validation
ALLOWED_PREFIXES = tuple()  # No restrictions

_REQUIRED_SUPPORTED_PARAMETERS = {"tools", "reasoning"}
_DEFAULT_WEB_SEARCH_PARAMETERS = {
    "engine": "auto",
    "max_results": 5,
    "max_total_results": 10,
    "search_context_size": "medium",
}
_MODELS_CACHE_TTL_SECONDS = 300
_models_cache_lock = threading.Lock()
_models_cache: Dict[str, Any] = {
    "loaded_at": 0.0,
    "by_id": {},
}


def _json_preview(value: Any, limit: int = 1200) -> str:
    """Serialize a value for safe, bounded log output."""
    try:
        text = json.dumps(value, ensure_ascii=False, default=str, sort_keys=True)
    except Exception as exc:
        text = f"<unserializable {type(value).__name__}: {exc}>"
    if len(text) > limit:
        return text[:limit] + "...[truncated]"
    return text


def _safe_log_fragment(value: Any, limit: int = 120) -> str:
    raw = str(value or "unknown").strip()
    if raw.startswith("openrouter:"):
        raw = raw[len("openrouter:"):]
    safe = "".join(ch if ch.isalnum() or ch in "-._" else "_" for ch in raw)
    return (safe or "unknown")[:limit]


def _redact_payload_log_headers(headers: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    secret_names = {"authorization", "x-api-key", "x-goog-api-key", "api-key"}
    redacted: Dict[str, Any] = {}
    for key, value in (headers or {}).items():
        if str(key).lower() in secret_names:
            redacted[key] = "***REDACTED***"
        else:
            redacted[key] = value
    return redacted



def _extract_usage_cost_value(value: Any) -> Optional[float]:
    if not isinstance(value, dict):
        return None
    usage = value.get("usage") if isinstance(value.get("usage"), dict) else value
    if not isinstance(usage, dict):
        return None
    raw_cost = usage.get("cost")
    if raw_cost is None or isinstance(raw_cost, bool):
        return None
    try:
        return float(raw_cost)
    except Exception:
        return None


def _combined_recovery_cost(primary_raw_json: Dict[str, Any], writer_raw_json: Optional[Dict[str, Any]]) -> Tuple[Optional[float], bool, Optional[float], Optional[float]]:
    primary_cost = _extract_usage_cost_value(primary_raw_json)
    writer_cost = _extract_usage_cost_value(writer_raw_json or {})
    if writer_raw_json is None:
        return primary_cost, primary_cost is not None, primary_cost, None
    if primary_cost is None or writer_cost is None:
        return None, False, primary_cost, writer_cost
    return primary_cost + writer_cost, True, primary_cost, writer_cost


def _summarize_openrouter_payload_for_log(payload: Dict[str, Any]) -> Dict[str, Any]:
    messages = payload.get("messages") if isinstance(payload, dict) else []
    messages = messages if isinstance(messages, list) else []
    tools = payload.get("tools") if isinstance(payload, dict) else []
    tools = tools if isinstance(tools, list) else []
    message_chars = 0
    roles: List[str] = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        role = str(message.get("role") or "message")
        if role not in roles:
            roles.append(role)
        content = message.get("content")
        if isinstance(content, str):
            message_chars += len(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and isinstance(block.get("text"), str):
                    message_chars += len(block.get("text") or "")
                elif isinstance(block, str):
                    message_chars += len(block)
        elif content is not None:
            try:
                message_chars += len(json.dumps(content, ensure_ascii=False, default=str))
            except Exception:
                message_chars += len(str(content))
    tool_types = []
    for tool in tools:
        if isinstance(tool, dict):
            tool_types.append(str(tool.get("type") or "unknown"))
    return {
        "model": payload.get("model") if isinstance(payload, dict) else None,
        "message_count": len(messages),
        "message_roles": roles,
        "message_content_chars": message_chars,
        "tool_count": len(tools),
        "tool_types": tool_types,
        "web_search_tool_count": sum(1 for item in tool_types if item == "openrouter:web_search"),
        "has_response_format": bool(payload.get("response_format")) if isinstance(payload, dict) else False,
        "sampling": {
            "max_tokens": payload.get("max_tokens") if isinstance(payload, dict) else None,
            "temperature": payload.get("temperature") if isinstance(payload, dict) else None,
            "top_p": payload.get("top_p") if isinstance(payload, dict) else None,
        },
        "reasoning_requested": bool(payload.get("reasoning")) if isinstance(payload, dict) else False,
    }


def _lightweight_response_summary(response_summary: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(response_summary, dict):
        return {}
    allowed = {
        "choice_count", "finish_reason", "content_present", "content_chars",
        "message_annotation_count", "content_annotation_count", "url_text_hits",
        "reasoning_tokens", "reasoning_chars", "web_search_requests", "tool_call_count",
    }
    return {key: copy.deepcopy(value) for key, value in response_summary.items() if key in allowed}


def _summarize_openrouter_response_for_log(response_json: Optional[Dict[str, Any]], response_summary: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(response_json, dict):
        return {"summary": _lightweight_response_summary(response_summary)}
    usage = response_json.get("usage") if isinstance(response_json.get("usage"), dict) else {}
    choice = _first_choice(response_json)
    message = choice.get("message") if isinstance(choice, dict) else {}
    message = message if isinstance(message, dict) else {}
    content = message.get("content")
    reasoning = message.get("reasoning") or message.get("thinking")
    annotations = message.get("annotations") if isinstance(message.get("annotations"), list) else []
    return {
        "id": response_json.get("id"),
        "model": response_json.get("model"),
        "provider": response_json.get("provider"),
        "choice_count": len(response_json.get("choices") or []) if isinstance(response_json.get("choices"), list) else 0,
        "first_finish_reason": choice.get("finish_reason") if isinstance(choice, dict) else None,
        "message_content_chars": len(content) if isinstance(content, str) else 0,
        "has_reasoning": bool(reasoning or message.get("reasoning_details")),
        "reasoning_chars": len(reasoning) if isinstance(reasoning, str) else None,
        "message_annotation_count": len(annotations),
        "has_tool_calls": bool(message.get("tool_calls")),
        "usage": {
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "total_tokens": usage.get("total_tokens"),
            "cost": usage.get("cost"),
            "server_tool_use": copy.deepcopy(usage.get("server_tool_use") or {}),
        },
        "summary": _lightweight_response_summary(response_summary),
    }

def _write_openrouter_payload_log(
    context: Optional[Dict[str, Any]],
    *,
    attempt: int,
    event: str,
    provider_url: str,
    payload: Dict[str, Any],
    headers: Optional[Dict[str, Any]],
    request_body_bytes: Optional[int] = None,
    response_code: Optional[int] = None,
    response_raw: Optional[str] = None,
    response_json: Optional[Dict[str, Any]] = None,
    response_summary: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
) -> Optional[str]:
    if not context or not context.get("enabled"):
        return None
    log_dir_raw = context.get("log_dir")
    if not log_dir_raw:
        return None
    try:
        log_dir = Path(str(log_dir_raw))
        log_dir.mkdir(parents=True, exist_ok=True)
        timestamp = time.strftime("%Y%m%dT%H%M%S", time.gmtime())
        millis = int((time.time() % 1) * 1000)
        run_id = _safe_log_fragment(context.get("run_id") or "run")
        model = context.get("model") or payload.get("model") or "unknown"
        event_safe = _safe_log_fragment(event, limit=40)
        model_safe = _safe_log_fragment(model)
        path = log_dir / f"{timestamp}{millis:03d}Z-{run_id}-attempt{attempt}-{event_safe}-{model_safe}.json"
        record: Dict[str, Any] = {
            "event": event,
            "attempt": attempt,
            "run_id": context.get("run_id"),
            "run_group_id": context.get("run_group_id"),
            "provider": context.get("provider") or "openrouter",
            "model": model,
            "provider_url": provider_url,
            "request": {
                "body_bytes": request_body_bytes,
                "headers": _redact_payload_log_headers(headers),
                "payload_summary": _summarize_openrouter_payload_for_log(payload),
            },
        }
        if response_code is not None or response_raw is not None or response_json is not None:
            record["response"] = {
                "status_code": response_code,
                "raw_chars": len(response_raw) if isinstance(response_raw, str) else None,
                "json_summary": _summarize_openrouter_response_for_log(response_json, response_summary),
            }
        if error:
            record["error"] = str(error)[:1000]
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(record, fh, indent=2, ensure_ascii=False, default=str)
        LOG.info("[OPENROUTER PAYLOAD LOG] wrote %s", path)
        return str(path)
    except Exception as exc:
        LOG.warning("[OPENROUTER PAYLOAD LOG] failed event=%s attempt=%s error=%s", event, attempt, exc)
        return None


def _normalize_model(model: str) -> str:
    """
    Normalize model ID. OpenRouter models use 'provider/model' format.
    Strip any 'openrouter:' prefix if present.
    """
    raw = model or ""
    if raw.startswith("openrouter:"):
        raw = raw[len("openrouter:"):]
    return raw


def _translate_sampling(cfg: Dict) -> Dict[str, Any]:
    """Translate FPF sampling parameters to OpenAI-compatible format."""
    out: Dict[str, Any] = {}

    if cfg.get("max_completion_tokens") is not None:
        out["max_tokens"] = int(cfg["max_completion_tokens"])
    elif cfg.get("max_tokens") is not None:
        out["max_tokens"] = int(cfg["max_tokens"])
    else:
        raise RuntimeError("OpenRouter requires 'max_tokens' or 'max_completion_tokens' in config - no fallback defaults allowed")

    if cfg.get("temperature") is not None:
        out["temperature"] = float(cfg["temperature"])
    if cfg.get("top_p") is not None:
        out["top_p"] = float(cfg["top_p"])

    return out


def _stringify_reasoning_value(value: Any) -> Optional[str]:
    """Convert provider reasoning payloads into a comparable string signal."""
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, dict):
        parts: List[str] = []
        for item in value.values():
            piece = _stringify_reasoning_value(item)
            if piece:
                parts.append(piece)
        if parts:
            return "\n\n".join(parts)
        if value:
            return "OpenRouter returned structured reasoning data."
    if isinstance(value, list):
        parts = []
        for item in value:
            piece = _stringify_reasoning_value(item)
            if piece:
                parts.append(piece)
        if parts:
            return "\n\n".join(parts)
        if value:
            return "OpenRouter returned structured reasoning data."
    return None


def _coerce_reasoning_effort(cfg: Dict[str, Any]) -> str:
    """Resolve the strict OpenRouter reasoning effort for this request."""
    allowed_efforts = {"minimal", "low", "medium", "high", "xhigh"}
    reasoning_cfg = cfg.get("reasoning") or cfg.get("thinking") or {}
    effort = None
    if isinstance(reasoning_cfg, dict):
        effort = reasoning_cfg.get("effort") or reasoning_cfg.get("reasoning_effort")
    if not effort:
        effort = cfg.get("reasoning_effort")
    if not effort:
        budget = cfg.get("thinking_budget_tokens")
        if budget is not None:
            if budget < 4000:
                effort = "low"
            elif budget > 12000:
                effort = "high"
            else:
                effort = "medium"
    effort = str(effort).strip().lower() if effort is not None else "high"
    if effort not in allowed_efforts:
        effort = "high"
    return effort


def _build_web_search_parameters(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Build strict OpenRouter server-tool search parameters."""
    params = dict(_DEFAULT_WEB_SEARCH_PARAMETERS)
    web_search_cfg = cfg.get("web_search") or {}
    if isinstance(web_search_cfg, dict):
        context_size = web_search_cfg.get("search_context_size")
        if isinstance(context_size, str) and context_size.strip().lower() in {"low", "medium", "high"}:
            params["search_context_size"] = context_size.strip().lower()

        max_results = web_search_cfg.get("max_results")
        if isinstance(max_results, int) and max_results > 0:
            params["max_results"] = max_results

        max_total_results = web_search_cfg.get("max_total_results")
        if isinstance(max_total_results, int) and max_total_results > 0:
            params["max_total_results"] = max_total_results

    if params["max_total_results"] < params["max_results"]:
        params["max_total_results"] = params["max_results"]
    return params


def _summarize_request_payload(payload: Dict[str, Any], headers: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Build a compact request summary for logs without leaking prompt text."""
    messages = payload.get("messages") or []
    message_summary = []
    for idx, message in enumerate(messages):
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if isinstance(content, str):
            content_length = len(content)
        elif isinstance(content, list):
            content_length = len(content)
        else:
            content_length = 0
        message_summary.append(
            {
                "index": idx,
                "role": message.get("role"),
                "content_type": type(content).__name__,
                "content_length": content_length,
            }
        )

    safe_header_keys = sorted((headers or {}).keys())
    return {
        "model": payload.get("model"),
        "message_count": len(messages),
        "messages": message_summary,
        "tool_types": [
            tool.get("type")
            for tool in (payload.get("tools") or [])
            if isinstance(tool, dict)
        ],
        "web_search_parameters": (
            payload.get("tools") or [{}]
        )[0].get("parameters") if payload.get("tools") else {},
        "tool_choice": payload.get("tool_choice"),
        "reasoning": payload.get("reasoning"),
        "response_format": payload.get("response_format"),
        "max_tokens": payload.get("max_tokens"),
        "temperature": payload.get("temperature"),
        "top_p": payload.get("top_p"),
        "header_keys": safe_header_keys,
        "has_authorization_header": "Authorization" in safe_header_keys,
    }


def _fetch_models_index(api_base: str = DEFAULT_MODELS_API_BASE) -> Dict[str, Dict[str, Any]]:
    """Fetch and cache OpenRouter model metadata for runtime capability checks."""
    now = time.time()
    with _models_cache_lock:
        loaded_at = float(_models_cache.get("loaded_at") or 0.0)
        by_id = _models_cache.get("by_id") or {}
        if by_id and (now - loaded_at) < _MODELS_CACHE_TTL_SECONDS:
            LOG.info(
                "[OPENROUTER CAPABILITIES] cache_hit models=%d age_seconds=%.1f",
                len(by_id),
                now - loaded_at,
            )
            return by_id

    url = api_base.rstrip("/") + "/models"
    base_delay_ms = 500
    max_delay_ms = 4000
    last_error: Optional[Exception] = None
    LOG.info("[OPENROUTER CAPABILITIES] cache_miss fetching=%s", url)

    for attempt in range(1, 4):
        req = urllib.request.Request(url, headers={"Content-Type": "application/json"}, method="GET")
        try:
            LOG.info("[OPENROUTER CAPABILITIES] attempt=%d/3 fetch_models", attempt)
            with urllib.request.urlopen(req, timeout=20) as resp:
                raw = resp.read().decode("utf-8")
                payload = json.loads(raw)
            data = payload.get("data") or []
            refreshed = {
                model["id"]: model
                for model in data
                if isinstance(model, dict) and isinstance(model.get("id"), str)
            }
            with _models_cache_lock:
                _models_cache["loaded_at"] = time.time()
                _models_cache["by_id"] = refreshed
            LOG.info(
                "[OPENROUTER CAPABILITIES] fetch_success models=%d sample=%s",
                len(refreshed),
                list(sorted(refreshed.keys()))[:5],
            )
            return refreshed
        except urllib.error.HTTPError as he:
            try:
                msg = he.read().decode("utf-8", errors="ignore")
            except Exception:
                msg = ""
            last_error = RuntimeError(
                f"OpenRouter models API error {getattr(he, 'code', '?')}: {getattr(he, 'reason', '?')} - {msg}"
            )
            if attempt < 3 and _is_transient_error(last_error):
                delay_ms = min(base_delay_ms * (2 ** (attempt - 1)), max_delay_ms)
                delay_ms = random.uniform(0, delay_ms)
                LOG.warning(
                    "[OPENROUTER CAPABILITIES] transient_failure attempt=%d/3 retry_in=%.2fs error=%s",
                    attempt,
                    delay_ms / 1000.0,
                    last_error,
                )
                time.sleep(delay_ms / 1000.0)
                continue
            LOG.error(
                "[OPENROUTER CAPABILITIES] fatal_http_failure attempt=%d/3 error=%s",
                attempt,
                last_error,
            )
            raise last_error from he
        except Exception as e:
            last_error = RuntimeError(f"OpenRouter models API request failed: {e}")
            if attempt < 3 and _is_transient_error(e):
                delay_ms = min(base_delay_ms * (2 ** (attempt - 1)), max_delay_ms)
                delay_ms = random.uniform(0, delay_ms)
                LOG.warning(
                    "[OPENROUTER CAPABILITIES] transient_exception attempt=%d/3 retry_in=%.2fs error=%s",
                    attempt,
                    delay_ms / 1000.0,
                    e,
                )
                time.sleep(delay_ms / 1000.0)
                continue
            LOG.error(
                "[OPENROUTER CAPABILITIES] fatal_exception attempt=%d/3 error=%s",
                attempt,
                e,
            )
            raise last_error from e

    if last_error:
        raise last_error
    raise RuntimeError("OpenRouter models API request failed after all retries")


def _get_model_metadata(model_to_use: str) -> Optional[Dict[str, Any]]:
    """Look up OpenRouter metadata for the normalized model id."""
    return _fetch_models_index().get(model_to_use)


def _assert_model_supports_strict_research(model_to_use: str) -> Dict[str, Any]:
    """Fail fast if the selected model cannot satisfy strict FPF requirements."""
    model_metadata = _get_model_metadata(model_to_use)
    if not isinstance(model_metadata, dict):
        LOG.error(
            "[OPENROUTER CAPABILITIES] missing_metadata model=%s",
            model_to_use,
        )
        raise RuntimeError(
            f"OpenRouter strict FPF could not find model metadata for '{model_to_use}'. "
            "Strict web search + reasoning enforcement requires a live capability record."
        )

    supported_parameters = set(model_metadata.get("supported_parameters") or [])
    missing = sorted(_REQUIRED_SUPPORTED_PARAMETERS - supported_parameters)
    LOG.info(
        "[OPENROUTER CAPABILITIES] model=%s required=%s supported_sample=%s missing=%s",
        model_to_use,
        sorted(_REQUIRED_SUPPORTED_PARAMETERS),
        sorted(supported_parameters)[:20],
        missing,
    )
    if missing:
        raise RuntimeError(
            f"OpenRouter strict FPF requires tools and reasoning support. "
            f"Model '{model_to_use}' is missing: {', '.join(missing)}."
        )
    return model_metadata


def build_payload(prompt: str, cfg: Dict) -> Tuple[Dict, Optional[Dict]]:
    """
    Build a strict OpenRouter chat completions payload.

    FPF always requests:
    - openrouter:web_search with engine=auto
    - reasoning enabled with an explicit effort level
    """
    model_cfg = cfg.get("model")
    if not model_cfg:
        raise RuntimeError("OpenRouter provider requires 'model' in config")
    model_to_use = _normalize_model(model_cfg)
    _assert_model_supports_strict_research(model_to_use)

    request_json = bool(cfg.get("json")) if cfg.get("json") is not None else False
    if request_json:
        json_instr = (
            "Return only a single valid JSON object. Do not include prose or fences. "
            "Output must be strictly valid JSON."
        )
        final_prompt = f"{json_instr}\n\n{prompt}"
    else:
        final_prompt = prompt

    sampling = _translate_sampling(cfg)

    messages: List[Dict[str, Any]] = []
    
    # Add system prompt if provided
    if cfg.get("system"):
        messages.append({"role": "system", "content": cfg["system"]})
    
    messages.append({"role": "user", "content": final_prompt})

    payload: Dict[str, Any] = {
        "model": model_to_use,
        "messages": messages,
        **sampling,
    }
    payload["tools"] = [
        {
            "type": "openrouter:web_search",
            "parameters": _build_web_search_parameters(cfg),
        }
    ]
    payload["reasoning"] = {
        "enabled": True,
        "effort": _coerce_reasoning_effort(cfg),
        "exclude": False,
    }

    # Optional: response_format for JSON mode
    if request_json:
        payload["response_format"] = {"type": "json_object"}

    # OpenRouter-specific headers (optional but recommended)
    headers: Dict[str, str] = {}
    
    # HTTP-Referer and X-Title for app identification (helps with rate limits)
    if cfg.get("http_referer"):
        headers["HTTP-Referer"] = cfg["http_referer"]
    if cfg.get("x_title"):
        headers["X-Title"] = cfg["x_title"]

    LOG.info(
        "[OPENROUTER REQUEST] Prepared strict payload: %s",
        _json_preview(_summarize_request_payload(payload, headers), limit=1800),
    )
    return payload, headers if headers else None


def _is_transient_error(exc: Exception) -> bool:
    """Check if an error is transient and worth retrying."""
    msg = str(exc).lower()
    transient = [
        "429",
        "rate limit",
        "timeout",
        "timed out",
        "500",
        "internal server error",
        "502",
        "503",
        "504",
        "connection",
        "network",
        "grounding",
        "validation",
        "reasoning",
        "web_search",
        "writer recovery",
        "no report content",
        "content missing",
        "extractable source evidence",
        "temporarily unavailable",
        "service unavailable",
        "overloaded",
    ]
    return any(tok in msg for tok in transient)


def extract_reasoning(raw_json: Dict) -> Optional[str]:
    """
    Extract reasoning/thinking from OpenRouter response.
    
    For models that support reasoning (o1/o3, DeepSeek R1, Gemini with thinking),
    the reasoning may appear in different places depending on the underlying model.
    """
    if not isinstance(raw_json, dict):
        return None

    # Check for explicit reasoning fields (DeepSeek R1 style)
    top_level_reasoning = _stringify_reasoning_value(raw_json.get("reasoning"))
    if top_level_reasoning:
        return top_level_reasoning
    top_level_reasoning_details = _stringify_reasoning_value(raw_json.get("reasoning_details"))
    if top_level_reasoning_details:
        return top_level_reasoning_details
    top_level_thinking = _stringify_reasoning_value(raw_json.get("thinking"))
    if top_level_thinking:
        return top_level_thinking

    # Check choices for reasoning content
    choices = raw_json.get("choices") or []
    for choice in choices:
        if not isinstance(choice, dict):
            continue
        
        message = choice.get("message") or {}
        
        # Some models put reasoning in a separate field
        message_reasoning = _stringify_reasoning_value(message.get("reasoning"))
        if message_reasoning:
            return message_reasoning
        message_reasoning_details = _stringify_reasoning_value(message.get("reasoning_details"))
        if message_reasoning_details:
            return message_reasoning_details
        message_thinking = _stringify_reasoning_value(message.get("thinking"))
        if message_thinking:
            return message_thinking
        
        # Check for reasoning in content blocks (Claude-style via OpenRouter)
        content = message.get("content")
        if isinstance(content, list):
            reasoning_parts = []
            for block in content:
                if isinstance(block, dict):
                    btype = block.get("type")
                    if btype in ("thinking", "reasoning"):
                        text = block.get("text") or block.get("thinking") or block.get("content")
                        if isinstance(text, str) and text.strip():
                            reasoning_parts.append(text.strip())
            if reasoning_parts:
                return "\n\n".join(reasoning_parts)

    usage = raw_json.get("usage") or {}
    completion_details = usage.get("completion_tokens_details") or {}
    output_details = usage.get("output_tokens_details") or {}
    reasoning_tokens = 0
    for details in (completion_details, output_details):
        try:
            reasoning_tokens = max(reasoning_tokens, int(details.get("reasoning_tokens") or 0))
        except Exception:
            continue
    if reasoning_tokens > 0:
        return f"OpenRouter reported {reasoning_tokens} reasoning tokens."

    return None


def _summarize_response_proof(raw_json: Dict[str, Any]) -> Dict[str, Any]:
    """Build a compact proof-oriented response summary for logs."""
    usage = raw_json.get("usage") or {}
    server_tool_use = usage.get("server_tool_use") or {}
    completion_details = usage.get("completion_tokens_details") or {}
    output_details = usage.get("output_tokens_details") or {}

    try:
        web_search_requests = int(server_tool_use.get("web_search_requests") or 0)
    except Exception:
        web_search_requests = 0

    reasoning_tokens = 0
    for details in (completion_details, output_details):
        try:
            reasoning_tokens = max(reasoning_tokens, int(details.get("reasoning_tokens") or 0))
        except Exception:
            continue

    message_annotation_count = 0
    content_annotation_count = 0
    url_text_hits = 0
    reasoning_block_count = 0
    message_reasoning_fields = 0
    choices = raw_json.get("choices") or []

    for choice in choices:
        if not isinstance(choice, dict):
            continue
        message = choice.get("message") or {}
        if not isinstance(message, dict):
            continue

        annotations = message.get("annotations")
        if isinstance(annotations, list):
            message_annotation_count += len(
                [
                    annotation
                    for annotation in annotations
                    if isinstance(annotation, dict)
                    and (
                        str(annotation.get("type") or "").lower() == "url_citation"
                        or isinstance(annotation.get("url_citation"), dict)
                        or (isinstance(annotation.get("url"), str) and annotation.get("url", "").strip())
                    )
                ]
            )

        if any(message.get(field) for field in ("reasoning", "reasoning_details", "thinking")):
            message_reasoning_fields += 1

        content = message.get("content")
        if isinstance(content, str):
            if "http://" in content or "https://" in content:
                url_text_hits += 1
        elif isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") in ("thinking", "reasoning"):
                    reasoning_block_count += 1
                block_annotations = block.get("annotations")
                if isinstance(block_annotations, list):
                    content_annotation_count += len(
                        [
                            annotation
                            for annotation in block_annotations
                            if isinstance(annotation, dict)
                            and (
                                str(annotation.get("type") or "").lower() == "url_citation"
                                or isinstance(annotation.get("url_citation"), dict)
                                or (isinstance(annotation.get("url"), str) and annotation.get("url", "").strip())
                            )
                        ]
                    )
                text = block.get("text")
                if isinstance(text, str) and ("http://" in text or "https://" in text):
                    url_text_hits += 1

    extracted_reasoning = extract_reasoning(raw_json)
    return {
        "top_level_keys": list(raw_json.keys()) if isinstance(raw_json, dict) else [],
        "choice_count": len(choices) if isinstance(choices, list) else 0,
        "usage_keys": list(usage.keys()) if isinstance(usage, dict) else [],
        "server_tool_use": server_tool_use,
        "web_search_requests": web_search_requests,
        "completion_tokens_details": completion_details,
        "output_tokens_details": output_details,
        "reasoning_tokens": reasoning_tokens,
        "message_annotation_count": message_annotation_count,
        "content_annotation_count": content_annotation_count,
        "url_text_hits": url_text_hits,
        "message_reasoning_fields": message_reasoning_fields,
        "reasoning_block_count": reasoning_block_count,
        "has_extracted_reasoning": bool(isinstance(extracted_reasoning, str) and extracted_reasoning.strip()),
        "extracted_reasoning_length": len(extracted_reasoning) if isinstance(extracted_reasoning, str) else 0,
    }


def _extract_response_text(raw_json: Dict[str, Any]) -> Optional[str]:
    """Extract only real assistant text content; never stringify the full JSON."""
    if not isinstance(raw_json, dict):
        return None

    choices = raw_json.get("choices") or []
    if not isinstance(choices, list) or not choices:
        return None

    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        return None

    message = first_choice.get("message") or {}
    if not isinstance(message, dict):
        return None

    content = message.get("content")
    if isinstance(content, str):
        text = content.strip()
        return text or None

    if isinstance(content, list):
        text_parts: List[str] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            text = None
            if block.get("type") == "text":
                text = block.get("text")
            elif isinstance(block.get("text"), str):
                text = block.get("text")
            if isinstance(text, str) and text.strip():
                text_parts.append(text.strip())
        if text_parts:
            return "\n\n".join(text_parts)

    return None


def _has_usable_report_content(raw_json: Dict[str, Any]) -> bool:
    """Content is usable only when real assistant text exists."""
    return bool(_extract_response_text(raw_json))


def _compact_source_item(item: Dict[str, Any], max_content_chars: int) -> Dict[str, Any]:
    compact: Dict[str, Any] = {}
    for key in ("url", "title", "content", "path", "kind"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            value = value.strip()
            if key == "content" and len(value) > max_content_chars:
                value = value[:max_content_chars] + "...[truncated]"
            compact[key] = value
    return compact



_WRITER_PROMPT_REQUEST_CHAR_BUDGET = 16000
_WRITER_PROMPT_REASONING_CHAR_BUDGET = 32000
_WRITER_PROMPT_EVIDENCE_CHAR_BUDGET = 64000

_CANONICAL_EVIDENCE_KEYS = {
    "annotation",
    "annotations",
    "citation",
    "citations",
    "reference",
    "references",
    "source",
    "sources",
    "url_citation",
    "url_citations",
    "search_result",
    "search_results",
    "web_search_result",
    "web_search_results",
}
_CANONICAL_URL_KEYS = {
    "url",
    "uri",
    "link",
    "href",
    "source_url",
    "citation_url",
    "web_url",
}
_CANONICAL_REASONING_KEYS = {
    "reasoning",
    "reasoning_details",
    "thinking",
    "thoughts",
}


def _json_path_child(path: str, key: Any) -> str:
    if isinstance(key, int):
        return f"{path}[{key}]"
    token = str(key).replace("~", "~0").replace("/", "~1")
    return f"{path}/{token}"


def _contains_url_text(value: Any) -> bool:
    return isinstance(value, str) and ("http://" in value or "https://" in value)


def _collect_canonical_evidence(value: Any, path: str = "$", out: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if out is None:
        out = {
            "annotations": [],
            "named_evidence": [],
            "urls": [],
            "url_text": [],
            "tool_evidence": [],
        }

    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key)
            lower_key = key_text.lower()
            child_path = _json_path_child(path, key_text)
            if lower_key in {"annotation", "annotations"}:
                out["annotations"].append({"path": child_path, "key": key_text, "value": copy.deepcopy(child)})
            if lower_key in _CANONICAL_EVIDENCE_KEYS:
                out["named_evidence"].append({"path": child_path, "key": key_text, "value": copy.deepcopy(child)})
            if lower_key in _CANONICAL_URL_KEYS and isinstance(child, str) and child.strip():
                out["urls"].append({"path": child_path, "key": key_text, "url": child.strip()})
            if lower_key in {"tool_call", "tool_calls", "tools"} and child:
                out["tool_evidence"].append({"path": child_path, "key": key_text, "value": copy.deepcopy(child)})
            if _contains_url_text(child):
                out["url_text"].append({"path": child_path, "text": child})
            _collect_canonical_evidence(child, child_path, out)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _collect_canonical_evidence(child, _json_path_child(path, index), out)
    elif _contains_url_text(value):
        out["url_text"].append({"path": path, "text": value})

    return out


def _extract_full_reasoning_packet(raw_json: Dict[str, Any]) -> Dict[str, Any]:
    nodes: List[Dict[str, Any]] = []

    def visit(value: Any, path: str) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                key_text = str(key)
                child_path = _json_path_child(path, key_text)
                if key_text.lower() in _CANONICAL_REASONING_KEYS:
                    text_value = _stringify_reasoning_value(child)
                    if text_value:
                        nodes.append(
                            {
                                "path": child_path,
                                "key": key_text,
                                "text": text_value,
                                "raw": copy.deepcopy(child),
                            }
                        )
                visit(child, child_path)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, _json_path_child(path, index))

    visit(raw_json, "$")
    if not nodes:
        fallback_reasoning = extract_reasoning(raw_json)
        if fallback_reasoning:
            nodes.append(
                {
                    "path": "$",
                    "key": "extract_reasoning",
                    "text": fallback_reasoning,
                    "raw": fallback_reasoning,
                }
            )

    parts: List[str] = []
    seen = set()
    for node in nodes:
        text_value = str(node.get("text") or "").strip()
        if text_value and text_value not in seen:
            parts.append(text_value)
            seen.add(text_value)
    full_text = "\n\n".join(parts)
    return {
        "text": full_text,
        "chars": len(full_text),
        "nodes": nodes,
    }


def _first_choice(raw_json: Dict[str, Any]) -> Dict[str, Any]:
    choices = raw_json.get("choices") if isinstance(raw_json, dict) else []
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        return choices[0]
    return {}


def _extract_response_cost_fields(raw_json: Dict[str, Any]) -> Dict[str, Any]:
    cost_fields: List[Dict[str, Any]] = []

    def visit(value: Any, path: str) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                key_text = str(key)
                lower_key = key_text.lower()
                child_path = _json_path_child(path, key_text)
                if any(token in lower_key for token in ("cost", "price", "credit", "charge", "billing")):
                    cost_fields.append({"path": child_path, "key": key_text, "value": copy.deepcopy(child)})
                visit(child, child_path)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, _json_path_child(path, index))

    visit(raw_json, "$")
    return {"fields": cost_fields}


def _writer_prompt_json(value: Any, *, char_budget: int, label: str) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, indent=2, default=str)
    except Exception as exc:
        text = f"<unserializable {label}: {exc}>"
    if len(text) <= char_budget:
        return text
    return (
        text[:char_budget]
        + f"\n...[truncated for writer prompt only: {label}; full value is not stored in production artifacts]"
    )


def _writer_prompt_text(value: Any, *, char_budget: int, label: str) -> str:
    text = str(value or "")
    if len(text) <= char_budget:
        return text
    return (
        text[:char_budget]
        + f"\n...[truncated for writer prompt only: {label}; full value is not stored in production artifacts]"
    )


def _request_metadata_for_research_packet(original_payload: Dict[str, Any]) -> Dict[str, Any]:
    messages = original_payload.get("messages") or []
    web_search_tools = []
    for tool in original_payload.get("tools") or []:
        if isinstance(tool, dict) and tool.get("type") == "openrouter:web_search":
            web_search_tools.append(copy.deepcopy(tool))
    return {
        "model": original_payload.get("model"),
        "message_count": len(messages) if isinstance(messages, list) else 0,
        "sampling": {
            "max_tokens": original_payload.get("max_tokens"),
            "temperature": original_payload.get("temperature"),
            "top_p": original_payload.get("top_p"),
        },
        "response_format": copy.deepcopy(original_payload.get("response_format")),
        "reasoning": copy.deepcopy(original_payload.get("reasoning")),
        "tools": copy.deepcopy(original_payload.get("tools") or []),
        "tool_choice": copy.deepcopy(original_payload.get("tool_choice")),
        "web_search_tools": web_search_tools,
    }


def _extract_validated_research_response_evidence(raw_json: Dict[str, Any]) -> Dict[str, Any]:
    canonical_evidence = _collect_canonical_evidence(raw_json)
    reasoning_packet = _extract_full_reasoning_packet(raw_json)
    usage = raw_json.get("usage") if isinstance(raw_json, dict) else {}
    usage = usage if isinstance(usage, dict) else {}
    server_tool_use = usage.get("server_tool_use") if isinstance(usage.get("server_tool_use"), dict) else {}
    web_search_requests = server_tool_use.get("web_search_requests")

    sources: List[Dict[str, Any]] = []
    for record in canonical_evidence.get("urls") or []:
        item = {"type": "url"}
        item.update(copy.deepcopy(record))
        sources.append(item)
    for record in canonical_evidence.get("annotations") or []:
        item = {"type": "annotation"}
        item.update(copy.deepcopy(record))
        sources.append(item)
    for record in canonical_evidence.get("named_evidence") or []:
        item = {"type": "named_evidence"}
        item.update(copy.deepcopy(record))
        sources.append(item)
    if not sources:
        for record in canonical_evidence.get("url_text") or []:
            item = {"type": "url_text"}
            item.update(copy.deepcopy(record))
            sources.append(item)

    return {
        "schema": "openrouter_fpf_validated_research_evidence_v1",
        "canonical_capture": True,
        "source_count": len(sources),
        "sources": sources,
        "web_search_requests": web_search_requests,
        "server_tool_use": copy.deepcopy(server_tool_use),
        "reasoning": reasoning_packet.get("text") or "",
        "reasoning_chars": reasoning_packet.get("chars") or 0,
        "reasoning_nodes": reasoning_packet.get("nodes") or [],
        "canonical_evidence": canonical_evidence,
        "usage": copy.deepcopy(usage),
        "cost": _extract_response_cost_fields(raw_json),
    }



def _build_lightweight_evidence_summary(evidence_bundle: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    evidence_bundle = evidence_bundle if isinstance(evidence_bundle, dict) else {}
    canonical_evidence = evidence_bundle.get("canonical_evidence") if isinstance(evidence_bundle.get("canonical_evidence"), dict) else {}
    def count_list(key: str) -> int:
        value = canonical_evidence.get(key)
        return len(value) if isinstance(value, list) else 0
    server_tool_use = evidence_bundle.get("server_tool_use") if isinstance(evidence_bundle.get("server_tool_use"), dict) else {}
    return {
        "schema": "openrouter_fpf_lightweight_evidence_summary_v1",
        "source_count": evidence_bundle.get("source_count") or 0,
        "web_search_requests": evidence_bundle.get("web_search_requests"),
        "server_tool_use": {"web_search_requests": server_tool_use.get("web_search_requests")},
        "reasoning_present": bool(evidence_bundle.get("reasoning_chars")),
        "reasoning_chars": evidence_bundle.get("reasoning_chars") or 0,
        "canonical_counts": {
            "urls": count_list("urls"),
            "annotations": count_list("annotations"),
            "named_evidence": count_list("named_evidence"),
            "url_text": count_list("url_text"),
        },
    }


def _sanitize_openrouter_response_for_persistence(raw_json: Dict[str, Any]) -> Dict[str, Any]:
    clean = copy.deepcopy(raw_json)
    choices = clean.get("choices") if isinstance(clean, dict) else []
    if isinstance(choices, list):
        for choice in choices:
            if not isinstance(choice, dict):
                continue
            message = choice.get("message")
            if not isinstance(message, dict):
                continue
            for key in (
                "reasoning", "reasoning_details", "thinking", "annotations", "tool_calls",
                "writer_recovery_reasoning", "writer_recovery_reasoning_details", "writer_recovery_thinking",
            ):
                message.pop(key, None)
    return clean


def _build_openrouter_fpf_status(
    *, original_payload: Dict[str, Any], primary_raw_json: Dict[str, Any], primary_response_summary: Dict[str, Any],
    evidence_bundle: Optional[Dict[str, Any]] = None, writer_raw_json: Optional[Dict[str, Any]] = None,
    writer_response_summary: Optional[Dict[str, Any]] = None, recovery_used: bool, recovery_status: str,
    content_available: bool, research_packet_saved: bool, error: Optional[str] = None,
) -> Dict[str, Any]:
    total_cost, cost_complete, primary_cost, writer_cost = _combined_recovery_cost(primary_raw_json, writer_raw_json if recovery_used else None)
    evidence_summary = _build_lightweight_evidence_summary(evidence_bundle)
    primary_choice = _first_choice(primary_raw_json)
    writer_choice = _first_choice(writer_raw_json or {})
    status: Dict[str, Any] = {
        "schema": "openrouter_fpf_status_v1",
        "provider": "openrouter",
        "model": original_payload.get("model") or primary_raw_json.get("model"),
        "validation_passed": True,
        "reasoning_required": True,
        "reasoning_seen": True,
        "reasoning_verified": True,
        "grounding_required": True,
        "web_search_required": True,
        "web_search_seen": True,
        "grounding_verified": True,
        "content_available": bool(content_available),
        "final_content_seen": bool(content_available),
        "research_packet_saved": bool(research_packet_saved),
        "recovery_used": bool(recovery_used),
        "recovery_status": recovery_status,
        "cost_complete": bool(cost_complete),
        "total_cost": total_cost,
        "primary_cost": primary_cost,
        "writer_cost": writer_cost,
        "primary_response_id": primary_raw_json.get("id") if isinstance(primary_raw_json, dict) else None,
        "writer_response_id": writer_raw_json.get("id") if isinstance(writer_raw_json, dict) else None,
        "primary_finish_reason": primary_choice.get("finish_reason") if isinstance(primary_choice, dict) else None,
        "writer_finish_reason": writer_choice.get("finish_reason") if isinstance(writer_choice, dict) else None,
        "evidence_summary": evidence_summary,
        "primary_response_summary": _lightweight_response_summary(primary_response_summary),
        "writer_response_summary": _lightweight_response_summary(writer_response_summary),
    }
    if error:
        status["error"] = str(error)[:1000]
    return status


def _write_openrouter_fpf_status(context: Optional[Dict[str, Any]], status: Dict[str, Any]) -> Optional[str]:
    if not context or not context.get("enabled"):
        return None
    log_dir_raw = context.get("log_dir")
    if not log_dir_raw:
        return None
    try:
        log_dir = Path(str(log_dir_raw))
        log_dir.mkdir(parents=True, exist_ok=True)
        path = log_dir / "openrouter_fpf_status.json"
        record: Dict[str, Any] = {
            "schema": "openrouter_fpf_status_artifact_v1",
            "updated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "run_id": context.get("run_id"),
            "run_group_id": context.get("run_group_id"),
        }
        record.update(status)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(record, fh, indent=2, ensure_ascii=False, default=str)
        LOG.info("[OPENROUTER FPF STATUS] wrote %s", path)
        return str(path)
    except Exception as exc:
        LOG.warning("[OPENROUTER FPF STATUS] failed error=%s", exc)
        return None

def _build_canonical_research_packet(
    *,
    original_payload: Dict[str, Any],
    primary_raw_json: Dict[str, Any],
    primary_response_summary: Dict[str, Any],
    writer_raw_json: Dict[str, Any],
    writer_response_summary: Dict[str, Any],
    evidence_bundle: Dict[str, Any],
    writer_content: str,
) -> Dict[str, Any]:
    primary_reasoning_packet = _extract_full_reasoning_packet(primary_raw_json)
    combined_usage = _merge_recovery_usage(primary_raw_json, writer_raw_json)
    primary_choice = _first_choice(primary_raw_json)
    writer_choice = _first_choice(writer_raw_json)
    return {
        "schema": "openrouter_fpf_lightweight_research_packet_v1",
        "provider": "openrouter",
        "model": original_payload.get("model") or primary_raw_json.get("model"),
        "original_request_summary": _summarize_openrouter_payload_for_log(original_payload),
        "primary_response_summary": _lightweight_response_summary(primary_response_summary),
        "primary_reasoning_present": bool(primary_reasoning_packet.get("text")),
        "primary_reasoning_chars": primary_reasoning_packet.get("chars") or 0,
        "primary_reasoning_node_count": len(primary_reasoning_packet.get("nodes") or []),
        "citation_evidence_summary": _build_lightweight_evidence_summary(evidence_bundle),
        "source_evidence_count": len(evidence_bundle.get("sources") or []),
        "request_metadata": _request_metadata_for_research_packet(original_payload),
        "search_metadata": {
            "web_search_requests": evidence_bundle.get("web_search_requests"),
            "server_tool_use": _build_lightweight_evidence_summary(evidence_bundle).get("server_tool_use"),
            "web_search_tools": copy.deepcopy(_request_metadata_for_research_packet(original_payload).get("web_search_tools") or []),
        },
        "usage": {
            "combined": copy.deepcopy(combined_usage),
        },
        "cost": {
            "primary": _combined_recovery_cost(primary_raw_json, writer_raw_json)[2],
            "writer": _combined_recovery_cost(primary_raw_json, writer_raw_json)[3],
            "total": _combined_recovery_cost(primary_raw_json, writer_raw_json)[0],
            "complete": _combined_recovery_cost(primary_raw_json, writer_raw_json)[1],
        },
        "validation": {
            "status": "passed",
            "gate": "primary_response_passed_grounding_and_reasoning_before_writer_recovery",
            "grounding": {
                "passed": True,
                "proof": _lightweight_response_summary(primary_response_summary),
            },
            "reasoning": {
                "passed": True,
                "full_reasoning_present": bool(primary_reasoning_packet.get("text")),
                "reasoning_chars": primary_reasoning_packet.get("chars") or 0,
            },
        },
        "completion": {
            "status": "recovered_from_validated_research_response_without_final_content",
            "primary_has_final_content": False,
            "writer_has_final_content": True,
            "writer_content_chars": len(writer_content or ""),
            "primary_finish_reason": primary_choice.get("finish_reason"),
            "writer_finish_reason": writer_choice.get("finish_reason"),
            "primary_response_id": primary_raw_json.get("id"),
            "writer_response_id": writer_raw_json.get("id"),
            "writer_response_summary": _lightweight_response_summary(writer_response_summary),
        },
    }

def _stringify_original_messages(payload: Dict[str, Any]) -> str:
    parts: List[str] = []
    messages = payload.get("messages") or []
    if isinstance(messages, list):
        for message in messages:
            if not isinstance(message, dict):
                continue
            role = str(message.get("role") or "message")
            content = message.get("content")
            if isinstance(content, str):
                text = content
            elif isinstance(content, list):
                text_parts = []
                for block in content:
                    if isinstance(block, dict) and isinstance(block.get("text"), str):
                        text_parts.append(block["text"])
                    elif isinstance(block, str):
                        text_parts.append(block)
                text = "\n".join(text_parts)
            else:
                text = json.dumps(content, ensure_ascii=False, default=str)
            if text and text.strip():
                parts.append(f"[{role}]\n{text.strip()}")
    return "\n\n".join(parts)



def _build_validated_research_writer_payload(original_payload: Dict[str, Any], evidence_bundle: Dict[str, Any]) -> Dict[str, Any]:
    original_request_for_prompt = {
        "model": original_payload.get("model"),
        "messages": copy.deepcopy(original_payload.get("messages") or []),
        "response_format": copy.deepcopy(original_payload.get("response_format")),
        "sampling": {
            "max_tokens": original_payload.get("max_tokens"),
            "temperature": original_payload.get("temperature"),
            "top_p": original_payload.get("top_p"),
        },
    }
    evidence_for_prompt = {
        "source_count": evidence_bundle.get("source_count"),
        "web_search_requests": evidence_bundle.get("web_search_requests"),
        "server_tool_use": copy.deepcopy(evidence_bundle.get("server_tool_use") or {}),
        "sources": copy.deepcopy(evidence_bundle.get("sources") or []),
        "canonical_evidence": copy.deepcopy(evidence_bundle.get("canonical_evidence") or {}),
    }
    primary_reasoning = evidence_bundle.get("reasoning") or ""

    writer_prompt = "\n\n".join(
        [
            "OpenRouter FPF validated research writer recovery.",
            "The primary OpenRouter research response already passed grounding and reasoning validation, but it did not contain final report text.",
            "Use only the original request, the primary reasoning, and the citation evidence below.",
            "Do not search. Do not call tools. Do not request or invent additional sources.",
            "Return final report text only. Do not return JSON metadata, markdown fences, tool calls, or process notes.",
            "Original request payload/messages:",
            _writer_prompt_json(
                original_request_for_prompt,
                char_budget=_WRITER_PROMPT_REQUEST_CHAR_BUDGET,
                label="original request",
            ),
            "Primary reasoning from the validated research response:",
            _writer_prompt_text(
                primary_reasoning,
                char_budget=_WRITER_PROMPT_REASONING_CHAR_BUDGET,
                label="primary reasoning",
            ),
            "Citation evidence from the validated research response:",
            _writer_prompt_json(
                evidence_for_prompt,
                char_budget=_WRITER_PROMPT_EVIDENCE_CHAR_BUDGET,
                label="citation evidence",
            ),
            "Write the final report now.",
        ]
    )

    writer_payload: Dict[str, Any] = {
        "model": original_payload.get("model"),
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a recovery-only OpenRouter writer for FPF. The research phase is complete and validation-gated. "
                    "Do not search, do not call tools, and output final report text only."
                ),
            },
            {"role": "user", "content": writer_prompt},
        ],
    }
    for key in ("max_tokens", "temperature", "top_p"):
        if original_payload.get(key) is not None:
            writer_payload[key] = original_payload.get(key)
    return writer_payload

def _merge_recovery_usage(primary: Dict[str, Any], writer: Dict[str, Any]) -> Dict[str, Any]:
    primary_usage = primary.get("usage") if isinstance(primary, dict) else {}
    writer_usage = writer.get("usage") if isinstance(writer, dict) else {}
    primary_usage = primary_usage if isinstance(primary_usage, dict) else {}
    writer_usage = writer_usage if isinstance(writer_usage, dict) else {}

    merged: Dict[str, Any] = dict(primary_usage)
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        values = []
        for usage in (primary_usage, writer_usage):
            try:
                values.append(int(usage.get(key) or 0))
            except Exception:
                values.append(0)
        if any(values):
            merged[key] = sum(values)

    total_cost, cost_complete, primary_cost, writer_cost = _combined_recovery_cost(primary, writer)
    if cost_complete:
        merged["cost"] = total_cost
    else:
        merged.pop("cost", None)

    merged["server_tool_use"] = primary_usage.get("server_tool_use") or {}
    merged["fpf_recovery_usage"] = {
        "primary": primary_usage,
        "writer": writer_usage,
        "primary_cost": primary_cost,
        "writer_cost": writer_cost,
        "total_cost": total_cost,
        "cost_complete": cost_complete,
    }
    return merged



def _combine_validated_research_writer_recovery_response(
    *,
    model: Any,
    original_payload: Dict[str, Any],
    primary_raw_json: Dict[str, Any],
    writer_raw_json: Dict[str, Any],
    evidence_bundle: Dict[str, Any],
    writer_content: str,
    primary_response_summary: Dict[str, Any],
    writer_response_summary: Dict[str, Any],
) -> Dict[str, Any]:
    combined = _sanitize_openrouter_response_for_persistence(primary_raw_json)
    writer_choice = _first_choice(writer_raw_json)
    writer_message = writer_choice.get("message") if isinstance(writer_choice, dict) else {}
    writer_message = writer_message if isinstance(writer_message, dict) else {}

    choices = combined.setdefault("choices", [])
    if not isinstance(choices, list):
        choices = []
        combined["choices"] = choices
    if not choices or not isinstance(choices[0], dict):
        choices.insert(0, {"index": 0, "message": {"role": "assistant"}})
    first_choice = choices[0]
    message = first_choice.setdefault("message", {})
    if not isinstance(message, dict):
        message = {"role": "assistant"}
        first_choice["message"] = message
    for key in (
        "reasoning", "reasoning_details", "thinking", "annotations", "tool_calls",
        "writer_recovery_reasoning", "writer_recovery_reasoning_details", "writer_recovery_thinking",
    ):
        message.pop(key, None)
    message["role"] = message.get("role") or "assistant"
    message["content"] = writer_content
    first_choice["finish_reason"] = writer_choice.get("finish_reason") or first_choice.get("finish_reason") or "stop"

    combined_usage = _merge_recovery_usage(primary_raw_json, writer_raw_json)
    research_packet = _build_canonical_research_packet(
        original_payload=original_payload,
        primary_raw_json=primary_raw_json,
        primary_response_summary=primary_response_summary,
        writer_raw_json=writer_raw_json,
        writer_response_summary=writer_response_summary,
        evidence_bundle=evidence_bundle,
        writer_content=writer_content,
    )

    combined["fpf_mode"] = "openrouter_validated_research_writer_recovery_v1"
    combined["provider"] = "openrouter"
    combined["model"] = combined.get("model") or model
    combined["usage"] = combined_usage
    combined["fpf_research_packet"] = research_packet
    combined["fpf_validated_research_writer_recovery"] = {
        "schema": "openrouter_fpf_validated_research_writer_recovery_v1",
        "writer_response_id": writer_raw_json.get("id") if isinstance(writer_raw_json, dict) else None,
        "validation_gate": {
            "stage": "primary_response",
            "status": "passed_before_recovery",
            "requires_grounding": True,
            "requires_reasoning": True,
            "primary_had_final_content": False,
        },
        "grounding_proof": {
            "stage": "primary_response",
            "passed": True,
            "evidence_count": evidence_bundle.get("source_count"),
            "web_search_requests": evidence_bundle.get("web_search_requests"),
        },
        "reasoning_proof": {
            "stage": "primary_response",
            "passed": True,
            "reasoning_chars": evidence_bundle.get("reasoning_chars"),
        },
        "writer_pass": {
            "tools_sent": False,
            "reasoning_required": False,
            "content_present": True,
            "response_summary": _lightweight_response_summary(writer_response_summary),
        },
        "canonical_research_packet_key": "fpf_research_packet",
        "evidence_summary": _build_lightweight_evidence_summary(evidence_bundle),
        "writer_response_summary": _lightweight_response_summary(writer_response_summary),
    }
    return combined


def _execute_validated_research_writer_recovery(
    *,
    provider_url: str,
    original_payload: Dict[str, Any],
    primary_raw_json: Dict[str, Any],
    primary_response_summary: Dict[str, Any],
    headers: Dict[str, Any],
    verify_helpers: Any,
    timeout: Optional[int],
    attempt: int,
    full_payload_log_context: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    evidence_bundle = _extract_validated_research_response_evidence(primary_raw_json)
    _write_openrouter_fpf_status(
        full_payload_log_context,
        _build_openrouter_fpf_status(
            original_payload=original_payload,
            primary_raw_json=primary_raw_json,
            primary_response_summary=primary_response_summary,
            evidence_bundle=evidence_bundle,
            recovery_used=True,
            recovery_status="started",
            content_available=False,
            research_packet_saved=False,
        ),
    )
    if not evidence_bundle.get("sources"):
        error = "OpenRouter validated research writer recovery refused: validated primary response had no extractable citation evidence."
        _write_openrouter_fpf_status(
            full_payload_log_context,
            _build_openrouter_fpf_status(
                original_payload=original_payload,
                primary_raw_json=primary_raw_json,
                primary_response_summary=primary_response_summary,
                evidence_bundle=evidence_bundle,
                recovery_used=True,
                recovery_status="failed",
                content_available=False,
                research_packet_saved=False,
                error=error,
            ),
        )
        raise RuntimeError(error)

    recovery_payload = _build_validated_research_writer_payload(original_payload, evidence_bundle)
    recovery_data = json.dumps(recovery_payload).encode("utf-8")

    LOG.warning(
        "[OPENROUTER VALIDATED RESEARCH WRITER RECOVERY] attempt=%d model=%s primary validation passed but content missing; source_count=%s web_search_requests=%s",
        attempt,
        original_payload.get("model"),
        evidence_bundle.get("source_count"),
        evidence_bundle.get("web_search_requests"),
    )
    _write_openrouter_payload_log(
        full_payload_log_context,
        attempt=attempt,
        event="validated_research_writer_recovery_request",
        provider_url=provider_url,
        payload=recovery_payload,
        headers=headers,
        request_body_bytes=len(recovery_data),
        response_summary={
            "primary_response_summary": primary_response_summary,
            "evidence": _build_lightweight_evidence_summary(evidence_bundle),
        },
    )

    req = urllib.request.Request(provider_url, data=recovery_data, headers=headers, method="POST")
    if timeout is None:
        resp_ctx = urllib.request.urlopen(req)
    else:
        resp_ctx = urllib.request.urlopen(req, timeout=timeout)
    with resp_ctx as resp:
        raw = resp.read().decode("utf-8")
        try:
            response_code = resp.getcode()
        except Exception:
            response_code = None
        writer_raw_json = json.loads(raw)

    writer_summary = _summarize_response_proof(writer_raw_json)
    _write_openrouter_payload_log(
        full_payload_log_context,
        attempt=attempt,
        event="validated_research_writer_recovery_response",
        provider_url=provider_url,
        payload=recovery_payload,
        headers=headers,
        request_body_bytes=len(recovery_data),
        response_code=response_code,
        response_raw=raw,
        response_json=writer_raw_json,
        response_summary=writer_summary,
    )

    writer_choice = _first_choice(writer_raw_json)
    writer_message = writer_choice.get("message") if isinstance(writer_choice, dict) else {}
    writer_message = writer_message if isinstance(writer_message, dict) else {}
    if writer_message.get("tool_calls"):
        error = "OpenRouter validated research writer recovery failed: recovery response returned tool calls despite tool-free writer request."
        _write_openrouter_fpf_status(
            full_payload_log_context,
            _build_openrouter_fpf_status(
                original_payload=original_payload,
                primary_raw_json=primary_raw_json,
                primary_response_summary=primary_response_summary,
                evidence_bundle=evidence_bundle,
                writer_raw_json=writer_raw_json,
                writer_response_summary=writer_summary,
                recovery_used=True,
                recovery_status="failed",
                content_available=False,
                research_packet_saved=False,
                error=error,
            ),
        )
        raise RuntimeError(error)

    writer_content = _extract_response_text(writer_raw_json)
    if not writer_content:
        error = "OpenRouter validated research writer recovery failed: recovery response had no report content."
        _write_openrouter_fpf_status(
            full_payload_log_context,
            _build_openrouter_fpf_status(
                original_payload=original_payload,
                primary_raw_json=primary_raw_json,
                primary_response_summary=primary_response_summary,
                evidence_bundle=evidence_bundle,
                writer_raw_json=writer_raw_json,
                writer_response_summary=writer_summary,
                recovery_used=True,
                recovery_status="failed",
                content_available=False,
                research_packet_saved=False,
                error=error,
            ),
        )
        raise RuntimeError(error)

    LOG.info(
        "[OPENROUTER VALIDATED RESEARCH WRITER RECOVERY] attempt=%d model=%s recovery passed content_length=%d source_count=%s",
        attempt,
        original_payload.get("model"),
        len(writer_content),
        evidence_bundle.get("source_count"),
    )
    combined = _combine_validated_research_writer_recovery_response(
        model=original_payload.get("model"),
        original_payload=original_payload,
        primary_raw_json=primary_raw_json,
        writer_raw_json=writer_raw_json,
        evidence_bundle=evidence_bundle,
        writer_content=writer_content,
        primary_response_summary=primary_response_summary,
        writer_response_summary=writer_summary,
    )
    _write_openrouter_fpf_status(
        full_payload_log_context,
        _build_openrouter_fpf_status(
            original_payload=original_payload,
            primary_raw_json=primary_raw_json,
            primary_response_summary=primary_response_summary,
            evidence_bundle=evidence_bundle,
            writer_raw_json=writer_raw_json,
            writer_response_summary=writer_summary,
            recovery_used=True,
            recovery_status="succeeded",
            content_available=True,
            research_packet_saved=True,
        ),
    )
    return combined

def parse_response(raw_json: Dict) -> str:
    """
    Parse the OpenRouter response to extract the main text content.
    Uses OpenAI-compatible format.
    """
    if not isinstance(raw_json, dict):
        return str(raw_json)

    text = _extract_response_text(raw_json)
    if text:
        return text

    mode = raw_json.get("fpf_mode")
    if mode == "openrouter_validated_research_writer_recovery_v1":
        raise RuntimeError("OpenRouter writer-recovery envelope has no final report content.")
    raise RuntimeError("OpenRouter response has no final report content; refusing to write raw provider JSON.")


def execute_and_verify(
    provider_url: str,
    payload: Dict,
    headers: Optional[Dict],
    verify_helpers,
    timeout: Optional[int] = None,
    max_retries: int = 3,
    retry_delay: float = 1.0,
    full_payload_log_context: Optional[Dict[str, Any]] = None,
) -> Dict:
    """
    Execute the OpenRouter request and run validation.
    """
    data = json.dumps(payload).encode("utf-8")
    hdrs = {"Content-Type": "application/json"}
    if headers:
        hdrs.update(headers)

    base_delay_ms = retry_delay * 1000
    max_delay_ms = max(base_delay_ms * 4, 120000)
    last_error: Optional[Exception] = None
    request_summary = _summarize_request_payload(payload, hdrs)
    LOG.info(
        "[OPENROUTER REQUEST] Starting validation-enabled request: %s",
        _json_preview(
            {
                "provider_url": provider_url,
                "timeout": timeout,
                "max_retries": max_retries,
                "request": request_summary,
            },
            limit=1800,
        ),
    )

    for attempt in range(1, max_retries + 1):
        req = urllib.request.Request(provider_url, data=data, headers=hdrs, method="POST")
        raw_for_attempt: Optional[str] = None
        response_code_for_attempt: Optional[int] = None
        try:
            LOG.info(
                "[OPENROUTER REQUEST] attempt=%d/%d model=%s timeout=%s",
                attempt,
                max_retries,
                payload.get("model"),
                timeout,
            )
            _write_openrouter_payload_log(
                full_payload_log_context,
                attempt=attempt,
                event="request",
                provider_url=provider_url,
                payload=payload,
                headers=hdrs,
                request_body_bytes=len(data),
            )
            if timeout is None:
                resp_ctx = urllib.request.urlopen(req)
            else:
                resp_ctx = urllib.request.urlopen(req, timeout=timeout)
            with resp_ctx as resp:
                raw = resp.read().decode("utf-8")
                raw_for_attempt = raw
                response_code = None
                try:
                    response_code = resp.getcode()
                except Exception:
                    response_code = None
                response_code_for_attempt = response_code
                raw_json = json.loads(raw)
                response_summary = _summarize_response_proof(raw_json)
                _write_openrouter_payload_log(
                    full_payload_log_context,
                    attempt=attempt,
                    event="response",
                    provider_url=provider_url,
                    payload=payload,
                    headers=hdrs,
                    request_body_bytes=len(data),
                    response_code=response_code,
                    response_raw=raw,
                    response_json=raw_json,
                    response_summary=response_summary,
                )
                LOG.info(
                    "[OPENROUTER RESPONSE] attempt=%d/%d status=%s summary=%s",
                    attempt,
                    max_retries,
                    response_code,
                    _json_preview(response_summary, limit=1800),
                )
                
                # Pass this module for provider-level flag checking
                provider_mod = sys.modules.get(__name__) or __import__(__name__)
                try:
                    verify_helpers.assert_grounding_and_reasoning(raw_json, provider=provider_mod)
                except verify_helpers.ValidationError as ve:
                    _write_openrouter_payload_log(
                        full_payload_log_context,
                        attempt=attempt,
                        event="validation_error",
                        provider_url=provider_url,
                        payload=payload,
                        headers=hdrs,
                        request_body_bytes=len(data),
                        response_code=response_code,
                        response_raw=raw,
                        response_json=raw_json,
                        response_summary=response_summary,
                        error=str(ve),
                    )
                    LOG.warning(
                        "[OPENROUTER VALIDATION] attempt=%d/%d failed missing_grounding=%s missing_reasoning=%s error=%s proof=%s",
                        attempt,
                        max_retries,
                        getattr(ve, "missing_grounding", None),
                        getattr(ve, "missing_reasoning", None),
                        ve,
                        _json_preview(response_summary, limit=1800),
                    )
                    raise
                LOG.info(
                    "[OPENROUTER VALIDATION] attempt=%d/%d passed model=%s web_search_requests=%s reasoning_tokens=%s annotations=%s url_hits=%s",
                    attempt,
                    max_retries,
                    payload.get("model"),
                    response_summary.get("web_search_requests"),
                    response_summary.get("reasoning_tokens"),
                    (response_summary.get("message_annotation_count") or 0)
                    + (response_summary.get("content_annotation_count") or 0),
                    response_summary.get("url_text_hits"),
                )
                if _has_usable_report_content(raw_json):
                    LOG.info(
                        "[OPENROUTER VALIDATED RESEARCH WRITER RECOVERY] attempt=%d/%d model=%s content present; recovery skipped",
                        attempt,
                        max_retries,
                        payload.get("model"),
                    )
                    _write_openrouter_payload_log(
                        full_payload_log_context,
                        attempt=attempt,
                        event="primary_content_present_after_validated_research",
                        provider_url=provider_url,
                        payload=payload,
                        headers=hdrs,
                        request_body_bytes=len(data),
                        response_code=response_code,
                        response_raw=raw,
                        response_json=raw_json,
                        response_summary=response_summary,
                    )
                    primary_evidence_bundle = _extract_validated_research_response_evidence(raw_json)
                    _write_openrouter_fpf_status(
                        full_payload_log_context,
                        _build_openrouter_fpf_status(
                            original_payload=payload,
                            primary_raw_json=raw_json,
                            primary_response_summary=response_summary,
                            evidence_bundle=primary_evidence_bundle,
                            recovery_used=False,
                            recovery_status="not_needed",
                            content_available=True,
                            research_packet_saved=False,
                        ),
                    )
                    return _sanitize_openrouter_response_for_persistence(raw_json)

                _write_openrouter_payload_log(
                    full_payload_log_context,
                    attempt=attempt,
                    event="primary_content_missing_after_validated_research",
                    provider_url=provider_url,
                    payload=payload,
                    headers=hdrs,
                    request_body_bytes=len(data),
                    response_code=response_code,
                    response_raw=raw,
                    response_json=raw_json,
                    response_summary=response_summary,
                    error="Primary response passed grounding/reasoning validation but had no final report content.",
                )
                try:
                    return _execute_validated_research_writer_recovery(
                        provider_url=provider_url,
                        original_payload=payload,
                        primary_raw_json=raw_json,
                        primary_response_summary=response_summary,
                        headers=hdrs,
                        verify_helpers=verify_helpers,
                        timeout=timeout,
                        attempt=attempt,
                        full_payload_log_context=full_payload_log_context,
                    )
                except Exception as exc:
                    _write_openrouter_fpf_status(
                        full_payload_log_context,
                        _build_openrouter_fpf_status(
                            original_payload=payload,
                            primary_raw_json=raw_json,
                            primary_response_summary=response_summary,
                            evidence_bundle=_extract_validated_research_response_evidence(raw_json),
                            recovery_used=True,
                            recovery_status="failed",
                            content_available=False,
                            research_packet_saved=False,
                            error=str(exc),
                        ),
                    )
                    raise
                
        except urllib.error.HTTPError as he:
            try:
                msg = he.read().decode("utf-8", errors="ignore")
            except Exception:
                msg = ""
            last_error = RuntimeError(f"HTTP error {getattr(he, 'code', '?')}: {getattr(he, 'reason', '?')} - {msg}")
            _write_openrouter_payload_log(
                full_payload_log_context,
                attempt=attempt,
                event="http_error",
                provider_url=provider_url,
                payload=payload,
                headers=hdrs,
                request_body_bytes=len(data),
                response_code=getattr(he, "code", None),
                response_raw=msg,
                error=str(last_error),
            )

            if attempt < max_retries and _is_transient_error(last_error):
                delay_ms = min(base_delay_ms * (2 ** (attempt - 1)), max_delay_ms)
                delay_ms = random.uniform(0, delay_ms)
                LOG.warning(
                    "[OPENROUTER RETRY] attempt=%d/%d retry_in=%.2fs reason=%s",
                    attempt,
                    max_retries,
                    delay_ms / 1000.0,
                    last_error,
                )
                time.sleep(delay_ms / 1000.0)
                continue
            LOG.error(
                "[OPENROUTER REQUEST] fatal_http_error attempt=%d/%d error=%s",
                attempt,
                max_retries,
                last_error,
            )
            raise last_error from he
        except Exception as e:
            last_error = RuntimeError(f"HTTP request failed: {e}")
            _write_openrouter_payload_log(
                full_payload_log_context,
                attempt=attempt,
                event="exception",
                provider_url=provider_url,
                payload=payload,
                headers=hdrs,
                request_body_bytes=len(data),
                response_code=response_code_for_attempt,
                response_raw=raw_for_attempt,
                error=str(last_error),
            )
            if attempt < max_retries and _is_transient_error(e):
                delay_ms = min(base_delay_ms * (2 ** (attempt - 1)), max_delay_ms)
                delay_ms = random.uniform(0, delay_ms)
                LOG.warning(
                    "[OPENROUTER RETRY] attempt=%d/%d retry_in=%.2fs exception=%s",
                    attempt,
                    max_retries,
                    delay_ms / 1000.0,
                    e,
                )
                time.sleep(delay_ms / 1000.0)
                continue
            LOG.error(
                "[OPENROUTER REQUEST] fatal_exception attempt=%d/%d error=%s",
                attempt,
                max_retries,
                e,
            )
            raise last_error from e

    if last_error:
        raise last_error
    raise RuntimeError("HTTP request failed after all retries")


def list_available_models(api_key: str, api_base: str = "https://openrouter.ai/api/v1") -> List[str]:
    """
    List available models from OpenRouter.
    
    OpenRouter provides a /models endpoint that returns all available models.
    """
    url = api_base.rstrip("/") + "/models"
    hdrs = {
        "Authorization": f"Bearer {api_key}",
    }
    req = urllib.request.Request(url, headers=hdrs, method="GET")
    with urllib.request.urlopen(req) as resp:
        raw = resp.read().decode("utf-8")
        data = json.loads(raw)
    
    models = []
    for m in data.get("data", []):
        if isinstance(m, dict) and m.get("id"):
            models.append(m["id"])
    return sorted(models)


if __name__ == "__main__":
    import argparse
    import os

    parser = argparse.ArgumentParser(description="OpenRouter provider utilities for FPF")
    parser.add_argument("--list-models", action="store_true", help="List available models using OPENROUTER_API_KEY")
    parser.add_argument("--api-base", default="https://openrouter.ai/api/v1", help="Override API base URL")

    args = parser.parse_args()

    if args.list_models:
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise SystemExit("OPENROUTER_API_KEY not set in environment")
        try:
            models = list_available_models(api_key, api_base=args.api_base)
            print(json.dumps(models, indent=2))
        except Exception as exc:
            raise SystemExit(f"Failed to list models: {exc}")
