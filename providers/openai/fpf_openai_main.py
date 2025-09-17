"""
OpenAI provider adapter for FPF (enforced web_search + reasoning).

This adapter enforces provider-side web_search and a high-level reasoning request
for every outgoing payload. The adapter provides:

- build_payload(prompt: str, cfg: dict) -> (dict, dict|None)
- parse_response(raw: dict) -> str
- extract_reasoning(raw: dict) -> Optional[str]
- validate_model(model_id: str) -> bool

Key guarantees implemented here:
- Web-search tooling (tools=[{"type": "web_search", ...}]) is always attached to the payload
  (for supported OpenAI models). The adapter will ignore any config flag intended to
  disable web_search.
- A reasoning object is always included in the payload (defaults to a "high" reasoning
  level if the config does not supply one).
- parse_response remains responsible for extracting readable text. extract_reasoning
  provides a deterministic way for callers to assert whether reasoning was returned.
"""

from __future__ import annotations
from typing import Dict, Tuple, Optional, Any, List

# Whitelist of models allowed for enforced web_search + reasoning.
# Only these models will be accepted by the OpenAI provider adapter.
ALLOWED_MODELS = {
    "gpt-5",
    "gpt-5-mini",
    "gpt-5-nano",
    "o4-mini",
    "o3",
    "o3-mini",
    "o1",
}


def _normalize_model(model: str) -> str:
    if not model:
        return ""
    return model.split(":")[0]


def validate_model(model_id: str) -> bool:
    m = _normalize_model(model_id or "")
    if m in ALLOWED_MODELS:
        return True
    for allowed in ALLOWED_MODELS:
        if m.startswith(allowed):
            return True
    return False


def _translate_sampling(cfg: Dict) -> Dict:
    out: Dict[str, Any] = {}
    if "max_output_tokens" in cfg and cfg["max_output_tokens"] is not None:
        out["max_output_tokens"] = int(cfg["max_output_tokens"])
    elif "max_completion_tokens" in cfg and cfg["max_completion_tokens"] is not None:
        out["max_output_tokens"] = int(cfg["max_completion_tokens"])
    elif "tokens" in cfg and cfg["tokens"] is not None:
        out["max_output_tokens"] = int(cfg["tokens"])

    if "temperature" in cfg and cfg["temperature"] is not None:
        out["temperature"] = float(cfg["temperature"])
    if "top_p" in cfg and cfg["top_p"] is not None:
        out["top_p"] = float(cfg["top_p"])

    reasoning = cfg.get("reasoning")
    if reasoning:
        out["reasoning"] = reasoning

    return out

def _attach_reasoning_for_model(payload: Dict[str, Any], cfg: Dict, model: str) -> None:
    """
    Attach a reasoning configuration to the payload based on the target model's capabilities.

    Strategy (heuristic / explicit mapping):
    - For models known to support `reasoning.effort` (o-series, gpt-5 family, some reasoning models)
      we set: payload["reasoning"] = {"effort": "<level>"} where level is one of low|medium|high.
    - For models that prefer `reasoning.max_tokens` (some adapters/providers), we set:
      payload["reasoning"] = {"max_tokens": <int>}
    - If the model is not known / mapping not available, raise RuntimeError so the caller can
      fail-fast rather than sending unsupported parameters.
    - The cfg may supply a `reasoning` object directly; if present we will use it (but still map/validate).
    """
    # Normalize incoming model string for simple prefix checks
    norm = model.split(":")[0] if model else ""

    # If caller explicitly provided a reasoning object, prefer it (but validate shape lightly)
    explicit = cfg.get("reasoning")
    if explicit:
        payload["reasoning"] = explicit
        return

    # Default reasoning level selection (can be tuned via cfg.web_search or other fields)
    # Prefer effort when supported.
    effort_level = cfg.get("reasoning", {}).get("effort", "high")

    # Heuristic mapping:
    # - gpt-5* and o1/o3/o4 series generally support `effort`
    # - gpt-4.1/gpt-4o-mini and some older models may not support effort
    # - If the model appears to be GPT-5 or o-series, use `effort`; otherwise prefer max_tokens when possible.
    if norm.startswith("gpt-5") or norm.startswith("o1") or norm.startswith("o3") or norm.startswith("o4"):
        # models that support `effort`
        payload["reasoning"] = {"effort": effort_level}
        return

    # Some providers/models prefer max_tokens-based reasoning (use conservative default)
    if norm.startswith("grok") or norm.startswith("anthropic") or norm.startswith("perplexity"):
        # map to max_tokens (example default 1500)
        payload["reasoning"] = {"max_tokens": 1500}
        return

    # For other gpt families where effort isn't supported (e.g., gpt-4.1), we cannot safely send reasoning
    # parameters without probing provider capabilities. Fail-fast per policy to avoid silent downgrade.
    raise RuntimeError(f"Model '{model}' does not have a known mapping for enforced reasoning parameters.") 


def build_payload(prompt: str, cfg: Dict) -> Tuple[Dict, Optional[Dict]]:
    """
    Build a Responses API payload that enforces web_search and reasoning.

    Returns (payload, optional_provider_headers)
    """
    model = cfg.get("model") or "gpt-4o-mini"
    model_to_use = model.split(":")[0] if ":" in model else model

    # Enforce provider whitelist: fail fast if the configured model is not allowed.
    if not validate_model(model_to_use):
        raise RuntimeError(f"Model '{model_to_use}' is not allowed by the OpenAI provider whitelist. Allowed models: {sorted(ALLOWED_MODELS)}")

    payload: Dict[str, Any] = {
        "model": model_to_use,
        "input": [
            {
                "role": "user",
                "content": prompt
            }
        ],
    }

    # Merge sampling / token params
    sampling = _translate_sampling(cfg)
    payload.update(sampling)

    # Enforce provider-side web_search (always on for supported models).
    # NOTE: Keep the tools block minimal to avoid passing provider-specific unknown params.
    # Tuning parameters (max_results, search_prompt, filters) may be accepted by some providers,
    # but including them inside the `tools` block has caused API errors (unknown_parameter).
    # Keep the tools block minimal and let provider adapters map tuning into supported fields.
    web_search_cfg = cfg.get("web_search", {}) or {}
    # NOTE: The web_search tool in the Responses API uses "web_search_preview"
    ws_tool: Dict[str, Any] = {"type": "web_search_preview"}

    # As of Sept 2025, the web_search tool only supports `search_context_size` for certain models.
    if model_to_use.startswith("gpt-5"):
        if "search_context_size" in web_search_cfg:
            ws_tool["search_context_size"] = web_search_cfg["search_context_size"]
    
    if "user_location" in web_search_cfg:
        ws_tool["user_location"] = web_search_cfg["user_location"]

    # Always attach the tools array and allow the model to choose tool usage.
    payload["tools"] = [ws_tool]
    payload["tool_choice"] = cfg.get("tool_choice", "auto")

    # Enforce reasoning in request via per-model mapping. This will raise a RuntimeError
    # if the selected model does not have a supported reasoning parameter mapping.
    _attach_reasoning_for_model(payload, cfg, model_to_use)

    include = cfg.get("include")
    if include:
        payload["include"] = include

    instructions = cfg.get("instructions")
    if instructions:
        payload["instructions"] = instructions

    return payload, None


def extract_reasoning(raw_json: Dict) -> Optional[str]:
    """
    Extract reasoning content from a Responses API response object if present.

    Returns a single string containing the reasoning text if found, otherwise None.
    """
    if not isinstance(raw_json, dict):
        return None

    # Top-level reasoning
    reasoning = raw_json.get("reasoning")
    if reasoning:
        if isinstance(reasoning, str) and reasoning.strip():
            return reasoning.strip()
        # if it's a dict, try to stringify relevant fields
        if isinstance(reasoning, dict):
            # attempt to join string fields
            parts: List[str] = []
            for v in reasoning.values():
                if isinstance(v, str) and v.strip():
                    parts.append(v.strip())
            if parts:
                return "\n\n".join(parts)

    # Check outputs list for reasoning-like fields
    output = raw_json.get("output") or raw_json.get("outputs")
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, dict):
                continue
            # some items may include a 'reasoning' field
            if "reasoning" in item and isinstance(item["reasoning"], (str, dict)):
                r = item["reasoning"]
                if isinstance(r, str) and r.strip():
                    return r.strip()
                if isinstance(r, dict):
                    parts = []
                    for v in r.values():
                        if isinstance(v, str) and v.strip():
                            parts.append(v.strip())
                    if parts:
                        return "\n\n".join(parts)
            # some content blocks may have a type indicating reasoning
            content = item.get("content") or item.get("contents")
            if isinstance(content, list):
                for c in content:
                    if isinstance(c, dict):
                        if c.get("type") in ("reasoning", "explanation") and isinstance(c.get("text"), str):
                            return c.get("text").strip()
    # No reasoning found
    return None


def parse_response(raw_json: Dict) -> str:
    """
    Extract readable text from a Responses API response object.

    This function prioritizes aggregated output_text and falls back to composing
    output parts. It does NOT decide whether reasoning was present (use extract_reasoning).
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

            if "choices" in raw_json and isinstance(raw_json["choices"], list) and raw_json["choices"]:
                ch = raw_json["choices"][0]
                if isinstance(ch, dict):
                    if "message" in ch and isinstance(ch["message"], dict):
                        msg = ch["message"]
                        content = msg.get("content")
                        if isinstance(content, str):
                            return content
                        if isinstance(content, list) and content and isinstance(content[0], str):
                            return content[0]
                    if "text" in ch and isinstance(ch["text"], str):
                        return ch["text"]

        import json as _json
        return _json.dumps(raw_json, indent=2, ensure_ascii=False)
    except Exception as e:
        import logging, json as _json
        logging.getLogger("fpf_openai_main").exception("Exception while parsing provider response: %s", e)
        try:
            logging.getLogger("fpf_openai_main").debug("Raw provider response: %s", _json.dumps(raw_json, indent=2, ensure_ascii=False))
        except Exception:
            logging.getLogger("fpf_openai_main").debug("Failed to serialize raw provider response for logging")
        raise RuntimeError("Failed to parse provider response") from e
