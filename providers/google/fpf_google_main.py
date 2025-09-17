"""
Google Gemini provider adapter for FPF.

This adapter enforces provider-side web_search for every outgoing payload.

- build_payload(prompt: str, cfg: dict) -> (dict, dict|None)
- parse_response(raw: dict) -> str
- extract_reasoning(raw: dict) -> Optional[str]
- validate_model(model_id: str) -> bool
"""

from __future__ import annotations
from typing import Dict, Tuple, Optional, Any, List

ALLOWED_MODELS = {
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash",
    "gemini-1.5-pro",
    "gemini-1.5-flash",
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


def build_payload(prompt: str, cfg: Dict) -> Tuple[Dict, Optional[Dict]]:
    """
    Build a Gemini API payload that enforces web_search.
    """
    model = cfg.get("model") or "gemini-2.5-pro"
    model_to_use = _normalize_model(model)

    if not validate_model(model_to_use):
        raise RuntimeError(f"Model '{model_to_use}' is not allowed by the Google provider whitelist. Allowed models: {sorted(ALLOWED_MODELS)}")

    payload: Dict[str, Any] = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ],
        "tools": [
            {
                "google_search": {}
            }
        ]
    }
    
    # Gemini uses 'generationConfig' for parameters like temperature, max_tokens etc.
    generation_config = {}
    if "max_completion_tokens" in cfg and cfg["max_completion_tokens"] is not None:
        generation_config["maxOutputTokens"] = int(cfg["max_completion_tokens"])
    
    if "temperature" in cfg and cfg["temperature"] is not None:
        generation_config["temperature"] = float(cfg["temperature"])

    if "top_p" in cfg and cfg["top_p"] is not None:
        generation_config["topP"] = float(cfg["top_p"])

    if generation_config:
        payload["generationConfig"] = generation_config

    return payload, None


def extract_reasoning(raw_json: Dict) -> Optional[str]:
    """
    Extract reasoning content from a Gemini API response object if present.
    For Gemini, we consider the webSearchQueries as the reasoning.
    """
    if not isinstance(raw_json, dict):
        return None

    try:
        grounding_metadata = raw_json.get("candidates")[0].get("groundingMetadata")
        if grounding_metadata and "webSearchQueries" in grounding_metadata:
            queries = grounding_metadata["webSearchQueries"]
            if queries:
                return "\n".join(queries)
    except (IndexError, KeyError, TypeError):
        return None

    return None


def parse_response(raw_json: Dict) -> str:
    """
    Extract readable text from a Gemini API response object.
    """
    if not isinstance(raw_json, dict):
        return str(raw_json)
        
    try:
        return raw_json["candidates"][0]["content"]["parts"][0]["text"]
    except (IndexError, KeyError, TypeError):
        import json
        return json.dumps(raw_json, indent=2)
