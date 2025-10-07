"""
OpenAI Deep Research provider adapter for FPF.

This adapter is intentionally separate from the standard OpenAI adapter to allow
different payload shapes and response parsing for the deep-research family.

Models supported (whitelist):
- o3-deep-research
- o4-mini-deep-research

Guarantees:
- Provider-side search/browse is requested (using a minimal tool entry).
- Reasoning is always requested (maps cfg.reasoning.effort -> reasoning.effort).
- parse_response extracts readable text; extract_reasoning returns a rationale string if found.
"""

from __future__ import annotations
from typing import Dict, Tuple, Optional, Any, List

# Whitelist of deep-research models
ALLOWED_MODELS = {
    "o3-deep-research",
    "o4-mini-deep-research",
}


def _normalize_model(model: str) -> str:
    if not model:
        return ""
    # Drop any suffix after ":" if present, keep base id for request compatibility
    return model.split(":", 1)[0]


def validate_model(model_id: str) -> bool:
    m = _normalize_model(model_id or "")
    if m in ALLOWED_MODELS:
        return True
    # Allow simple prefix tolerance for revisions, e.g., "o3-deep-research-2025-09-01"
    for allowed in ALLOWED_MODELS:
        if m.startswith(allowed):
            return True
    return False


def _translate_sampling(cfg: Dict, model: str) -> Dict:
    """
    Translate generic config knobs into deep-research friendly fields.
    We keep this minimal and conservative to avoid unknown parameter errors.
    """
    out: Dict[str, Any] = {}
    # Prefer provider-agnostic max_completion_tokens
    if "max_completion_tokens" in cfg and cfg["max_completion_tokens"] is not None:
        # OpenAI Responses API commonly uses "max_output_tokens"
        out["max_output_tokens"] = int(cfg["max_completion_tokens"])

    # Common sampling controls (optional; only map when set)
    if "top_p" in cfg and cfg["top_p"] is not None:
        out["top_p"] = float(cfg["top_p"])


    return out


def _attach_reasoning(payload: Dict[str, Any], cfg: Dict, model: str) -> None:
    """
    Attach a reasoning configuration. Deep-research models should accept an 'effort' level,
    but if that changes, this is the single place to update.
    """
    # Hard enforce reasoning.effort for DP models at adapter level (non-configurable)
    payload["reasoning"] = {"effort": "medium"}


def build_payload(prompt: str, cfg: Dict) -> Tuple[Dict, Optional[Dict]]:
    """
    Build a request payload for deep-research models.

    Current strategy:
    - Use a Responses-API-compatible shape with a minimal search tool (web_search_preview)
      and tool_choice='auto'. If the deep-research API diverges, adapt this function only.
    """
    model_cfg = cfg.get("model") or "o3-deep-research"
    model_to_use = _normalize_model(model_cfg)

    if not validate_model(model_to_use):
        raise RuntimeError(
            f"Model '{model_to_use}' is not allowed by the OpenAI Deep Research provider whitelist. "
            f"Allowed models: {sorted(ALLOWED_MODELS)}"
        )

    payload: Dict[str, Any] = {
        "model": model_to_use,
        "input": [
            {
                "role": "user",
                "content": prompt,
            }
        ],
    }

    # Merge sampling parameters (max tokens, top_p, direct reasoning object)
    sampling = _translate_sampling(cfg, model_to_use)
    payload.update(sampling)

    # Always attach a minimal search tool request. Keep this narrow to avoid unknown params.
    # Using the same tool name as the OpenAI Responses API for now; adjust if deep-research
    # uses a different tool-type or a dedicated browse flag.
    ws_tool: Dict[str, Any] = {"type": "web_search_preview"}

    # Deep-research models require 'medium' search_context_size
    ws_tool["search_context_size"] = "medium"

    payload["tools"] = [ws_tool]
    payload["tool_choice"] = cfg.get("tool_choice", "auto")

    # Ensure reasoning is attached if not already (maps cfg.reasoning.effort by default)
    _attach_reasoning(payload, cfg, model_to_use)

    # Optional fields
    include = cfg.get("include")
    if include:
        payload["include"] = include

    instructions = cfg.get("instructions")
    if instructions:
        payload["instructions"] = instructions

    # Enforce JSON-only responses when configured
    if cfg.get("json") is True:
        payload["response_format"] = {"type": "json_object"}

    # No special headers required here; file_handler sets Authorization or provider-specific headers
    return payload, None


def extract_reasoning(raw_json: Dict) -> Optional[str]:
    """
    Extract a rationale string from a deep-research style response.

    Accept multiple shapes:
    - top-level 'reasoning' (str or dict)
    - outputs[*].reasoning
    - content blocks with type in {'reasoning','analysis','explanation'}
    - deep-research hints: 'research_steps', 'plan', 'queries' (flattened)
    """
    if not isinstance(raw_json, dict):
        return None

    # 1) direct top-level
    r = raw_json.get("reasoning")
    if isinstance(r, str) and r.strip():
        return r.strip()
    if isinstance(r, dict):
        parts: List[str] = []
        for v in r.values():
            if isinstance(v, str) and v.strip():
                parts.append(v.strip())
        if parts:
            return "\n\n".join(parts)

    # 2) outputs list scanning
    output = raw_json.get("output") or raw_json.get("outputs")
    if isinstance(output, list):
        # collect first plausible rationale
        for item in output:
            if not isinstance(item, dict):
                continue
            # explicit reasoning field
            if "reasoning" in item:
                ri = item["reasoning"]
                if isinstance(ri, str) and ri.strip():
                    return ri.strip()
                if isinstance(ri, dict):
                    parts = []
                    for v in ri.values():
                        if isinstance(v, str) and v.strip():
                            parts.append(v.strip())
                    if parts:
                        return "\n\n".join(parts)
            # content blocks tagged as reasoning/analysis
            content = item.get("content") or item.get("contents")
            if isinstance(content, list):
                for c in content:
                    if isinstance(c, dict):
                        t = c.get("type")
                        if t in {"reasoning", "analysis", "explanation"} and isinstance(c.get("text"), str):
                            return c.get("text").strip()

    # 3) deep-research hints
    for key in ("research_steps", "plan", "queries"):
        v = raw_json.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
        if isinstance(v, list):
            joined = "\n".join([s for s in v if isinstance(s, str) and s.strip()])
            if joined.strip():
                return joined.strip()

    return None


def parse_response(raw_json: Dict) -> str:
    """
    Extract readable assistant text from a deep-research response.

    Strategy:
    - Prefer 'output_text' if present.
    - Otherwise join any textual content from outputs[*].content parts (type text/output_text).
    - As a fallback, render a short markdown summary with model/usage and append reasoning (if available).
    """
    try:
        if isinstance(raw_json, dict):
            if "output_text" in raw_json and isinstance(raw_json["output_text"], str):
                return raw_json["output_text"]

            output = raw_json.get("output") or raw_json.get("outputs")
            if isinstance(output, list) and output:
                parts: List[str] = []
                for item in output:
                    if not isinstance(item, dict):
                        continue
                    content = item.get("content") or item.get("contents")
                    if isinstance(content, list):
                        for c in content:
                            if isinstance(c, dict):
                                if c.get("type") in ("output_text", "text") and isinstance(c.get("text"), str):
                                    parts.append(c.get("text"))
                                elif "text" in c and isinstance(c["text"], str):
                                    parts.append(c["text"])
                            elif isinstance(c, str):
                                parts.append(c)
                    if "text" in item and isinstance(item["text"], str):
                        parts.append(item["text"])
                if parts:
                    return "\n\n".join(parts)

        # Markdown fallback summarizing key fields
        status = raw_json.get("status") if isinstance(raw_json, dict) else None
        r_model = raw_json.get("model") if isinstance(raw_json, dict) else None
        u = (raw_json.get("usage") or {}) if isinstance(raw_json, dict) else {}
        it = u.get("input_tokens") or u.get("prompt_tokens")
        ot = u.get("output_tokens") or u.get("completion_tokens")
        tt = u.get("total_tokens")

        try:
            reasoning_text = extract_reasoning(raw_json)
        except Exception:
            reasoning_text = None

        lines: List[str] = []
        lines.append("# Response")
        if r_model:
            lines.append(f"- Model: {r_model}")
        if status:
            lines.append(f"- Status: {status}")

        if any(isinstance(x, int) for x in (it, ot, tt)):
            lines.append("## Usage")
            if isinstance(it, int):
                lines.append(f"- Input tokens: {it}")
            if isinstance(ot, int):
                lines.append(f"- Output tokens: {ot}")
            if isinstance(tt, int):
                lines.append(f"- Total tokens: {tt}")

        if reasoning_text and isinstance(reasoning_text, str) and reasoning_text.strip():
            lines.append("## Reasoning")
            lines.append(reasoning_text.strip())

        if len(lines) <= 1:
            return "No assistant text was returned. See logs for details."
        return "\n".join(lines)
    except Exception as e:
        import logging, json as _json
        logging.getLogger("fpf_openaidp_main").exception("Exception while parsing deep-research response: %s", e)
        try:
            logging.getLogger("fpf_openaidp_main").debug("Raw provider response: %s", _json.dumps(raw_json, indent=2, ensure_ascii=False))
        except Exception:
            logging.getLogger("fpf_openaidp_main").debug("Failed to serialize raw provider response for logging")
        raise RuntimeError("Failed to parse deep-research provider response") from e


# --- Background execution for DP models (OpenAI Responses background mode) ---

from typing import Dict

def execute_dp_background(provider_url: str, payload: Dict, headers: Dict, timeout: int = 7200) -> Dict:
    """
    Submit a deep-research request with background=True and poll the Responses API
    until completion. Returns the final response JSON dict.

    Console prints are always-on and redact secrets; long JSON is truncated.
    """
    import urllib.request
    import urllib.error
    import json as _json
    import time as _time

    def _redact_headers(h: dict) -> dict:
        try:
            red = {}
            for k, v in (h or {}).items():
                lk = str(k).lower()
                if lk in ("authorization", "x-api-key", "x-goog-api-key", "api-key"):
                    red[k] = "***REDACTED***"
                else:
                    red[k] = v
            return red
        except Exception:
            return {}

    def _truncate(s: str, n: int = 2000) -> str:
        try:
            if s is None:
                return ""
            s = str(s)
            return s if len(s) <= n else s[:n] + "…"
        except Exception:
            return ""

    # 1) Submit with background=True
    body = dict(payload or {})
    body["background"] = True
    data = _json.dumps(body).encode("utf-8")
    hdrs = {"Content-Type": "application/json"}
    if headers:
        hdrs.update(headers)

    try:
        print(f"[FPF DP][REQ] POST {provider_url} headers={_redact_headers(hdrs)} payload_bytes={len(data)} preview={_truncate(_json.dumps(body))}", flush=True)
    except Exception:
        pass

    req = urllib.request.Request(provider_url, data=data, headers=hdrs, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            status_code = getattr(resp, "status", resp.getcode() if hasattr(resp, "getcode") else "unknown")
            try:
                print(f"[FPF DP][RESP] {provider_url} status={status_code} bytes={len(raw)} preview={_truncate(raw)}", flush=True)
            except Exception:
                pass
            submit_json = _json.loads(raw)
    except urllib.error.HTTPError as he:
        try:
            msg = he.read().decode("utf-8", errors="ignore")
        except Exception:
            msg = ""
        print(f"[FPF DP][ERR] {provider_url} status={getattr(he,'code','?')} reason={getattr(he,'reason','?')} body={_truncate(msg)}", flush=True)
        raise
    except Exception as e:
        print(f"[FPF DP][ERR] {provider_url} error={e}", flush=True)
        raise

    # Expect an id to poll
    response_id = submit_json.get("id")
    if not response_id:
        raise RuntimeError("Background submit did not return an 'id' to poll")

    print(f"[FPF DP][SUBMIT] response_id={response_id}", flush=True)

    # 2) Poll status until completed/failed/timeout
    poll_url = provider_url.rstrip("/") + "/" + response_id
    start_ts = _time.time()
    polling_interval = 15
    max_polls = int((timeout // polling_interval) if timeout and timeout > 0 else 120)

    for i in range(max_polls):
        try:
            get_req = urllib.request.Request(poll_url, headers=_redact_headers(hdrs), method="GET")
            # Re-apply Authorization header (redacted above for print, but real header must be present)
            # Use original hdrs for the actual request
            get_req = urllib.request.Request(poll_url, headers=hdrs, method="GET")
            with urllib.request.urlopen(get_req, timeout=polling_interval + 10) as r:
                raw_status = r.read().decode("utf-8")
                status_json = _json.loads(raw_status)
        except urllib.error.HTTPError as he:
            try:
                msg = he.read().decode("utf-8", errors="ignore")
            except Exception:
                msg = ""
            print(f"[FPF DP][POLL ERR] id={response_id} status={getattr(he,'code','?')} reason={getattr(he,'reason','?')} body={_truncate(msg)}", flush=True)
            raise
        except Exception as e:
            print(f"[FPF DP][POLL ERR] id={response_id} error={e}", flush=True)
            raise

        status = status_json.get("status")
        elapsed = _time.time() - start_ts
        print(f"[FPF DP][POLL] id={response_id} status={status} elapsed={elapsed:.1f}s", flush=True)

        if status == "completed":
            print(f"[FPF DP][COMPLETE] id={response_id} elapsed={elapsed:.1f}s", flush=True)
            return status_json
        if status in ("failed", "cancelled", "canceled"):
            raise RuntimeError(f"Background DP task {status} (id={response_id})")

        _time.sleep(polling_interval)

    raise RuntimeError(f"Background DP task timed out after {int(elapsed)}s (id={response_id})")
