"""
google_adapter.py

Full Google Gemini (Generative) provider-side grounding adapter.

Behavior:
- Attempts to call Google's Generative API (Gemini) to perform provider-side grounding.
- Supports two authentication methods:
  1. Application Default Credentials (google.auth) -> uses OAuth2 bearer token
  2. API key (provider_conf.api_key or env GOOGLE_API_KEY) -> uses ?key=API_KEY query param
- Builds a conservative request body and attempts to extract text and citation/source data
  from common response shapes. Providers and API versions vary; this is best-effort.
- Retries once on transient failures.

Changes made:
- Concatenate multiple text parts from response candidates/content and output arrays instead of returning only the first part.
- Save the raw provider JSON response to a timestamped file (API_Cost_Multiplier/temp_grounding_responses/)
  for debugging before any extraction or truncation happens.
- Removed the hard 2000-char fallback truncation. If extraction heuristics fail, the adapter will
  fall back to the full JSON (stringified), and the raw file will contain the complete provider payload
  for inspection.
"""

import os
import time
import json
import logging
from datetime import datetime
from typing import Tuple, List

try:
    import requests
except Exception:
    requests = None

# Optional Google auth flow
try:
    import google.auth
    import google.auth.transport.requests
    _HAS_GOOGLE_AUTH = True
except Exception:
    _HAS_GOOGLE_AUTH = False


def _ensure_debug_dir() -> str:
    """
    Ensure a repo-local debug directory exists and return its path.
    """
    # Use CWD as repo root (script invoked from project). Place debug files under API_Cost_Multiplier/temp_grounding_responses
    base = os.path.join(os.getcwd(), "API_Cost_Multiplier", "temp_grounding_responses")
    try:
        os.makedirs(base, exist_ok=True)
    except Exception:
        pass
    return base


def _save_raw_response(resp_json: dict, provider: str, model: str, logger=None) -> str:
    """
    Save the raw JSON response to a timestamped file for debugging.
    Returns the file path (or empty string on failure).
    """
    logger = logger or logging.getLogger("gpt_processor.google_adapter")
    try:
        debug_dir = _ensure_debug_dir()
        ts = datetime.utcnow().strftime("%Y%m%dT%H%M%S.%fZ")
        fname = f"{provider}_{model}_{ts}.json".replace(" ", "_")
        path = os.path.join(debug_dir, fname)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(resp_json, f, ensure_ascii=False, indent=2)
        if logger:
            logger.debug(f"Saved raw provider response to {path}")
        return path
    except Exception as e:
        if logger:
            logger.debug(f"Failed to save raw response: {e}")
        return ""


def _concat_text_from_content_list(content_list: List) -> str:
    """
    Given a content list (as sometimes returned by Gemini candidates/content),
    concatenate text-like parts into a single string.
    """
    pieces = []
    for part in content_list:
        try:
            if isinstance(part, dict):
                # Common dict forms have 'type' and text fields
                ttype = part.get("type", "").lower()
                if ttype in ("output_text", "text", "message", "assistant", "assistant_output"):
                    # try common fields
                    text = part.get("text") or part.get("content") or part.get("message") or ""
                    if isinstance(text, list):
                        # if nested list, join inner text elements
                        for it in text:
                            if isinstance(it, dict):
                                possible = it.get("text") or it.get("content") or ""
                                if possible:
                                    pieces.append(str(possible))
                            else:
                                pieces.append(str(it))
                    elif text:
                        pieces.append(str(text))
                else:
                    # sometimes a dict contains a 'text' key even if type is unexpected
                    text = part.get("text") or part.get("content")
                    if text:
                        if isinstance(text, list):
                            for it in text:
                                pieces.append(str(it))
                        else:
                            pieces.append(str(text))
            elif isinstance(part, str):
                pieces.append(part)
            else:
                # fallback: stringify
                pieces.append(str(part))
        except Exception:
            continue
    return "\n".join([p.strip() for p in pieces if p is not None and p != ""])


def _extract_text_and_sources_from_response(resp_json, logger=None):
    """
    Try several common response shapes for the Google Generative API and extract:
    - text: the generated assistant text (concatenated across parts if necessary)
    - sources: list of {title, url, snippet}
    Returns (text, sources)
    """
    logger = logger or logging.getLogger("gpt_processor.google_adapter")
    text_parts = []
    sources = []

    try:
        # Save raw provider response for debugging before extraction
        try:
            _save_raw_response(resp_json, "google", resp_json.get("model", "unknown") if isinstance(resp_json, dict) else "unknown", logger=logger)
        except Exception:
            pass

        if isinstance(resp_json, dict):
            # Pattern: {'candidates': [{'output': '...', 'content': [...]}, ...], ...}
            if "candidates" in resp_json and isinstance(resp_json["candidates"], list):
                for cand in resp_json["candidates"]:
                    if isinstance(cand, dict):
                        # Try 'output' (string)
                        out_str = cand.get("output")
                        if isinstance(out_str, str) and out_str.strip():
                            text_parts.append(out_str.strip())
                        # Try 'content' list (concatenate parts)
                        content = cand.get("content")
                        if isinstance(content, list) and content:
                            part_text = _concat_text_from_content_list(content)
                            if part_text:
                                text_parts.append(part_text)
                        # Some candidates embed nested 'content' under other keys
                        # inspect common nested places
                        for key in ("content", "output", "text"):
                            val = cand.get(key)
                            if isinstance(val, list) and val:
                                part_text = _concat_text_from_content_list(val)
                                if part_text:
                                    text_parts.append(part_text)

            # Top-level 'output' structure: may be string or dict with 'content' list
            if "output" in resp_json:
                out = resp_json["output"]
                if isinstance(out, str) and out.strip():
                    text_parts.append(out.strip())
                elif isinstance(out, dict):
                    content = out.get("content")
                    if isinstance(content, list) and content:
                        part_text = _concat_text_from_content_list(content)
                        if part_text:
                            text_parts.append(part_text)

            # Legacy shapes: 'response' -> 'text'
            if "response" in resp_json and isinstance(resp_json["response"], dict):
                rtext = resp_json["response"].get("text")
                if rtext:
                    text_parts.append(rtext.strip())

            # Attempt to find text in other common nested shapes
            # Walk some nested fields heuristically
            for maybe in ("candidates", "output", "response", "result", "content"):
                node = resp_json.get(maybe)
                if isinstance(node, list):
                    # concatenate if possible
                    for item in node:
                        if isinstance(item, dict):
                            # look for nested 'content' or 'output'
                            if "content" in item and isinstance(item["content"], list):
                                t = _concat_text_from_content_list(item["content"])
                                if t:
                                    text_parts.append(t)
                            elif "output" in item and isinstance(item["output"], str):
                                text_parts.append(item["output"].strip())

            # Extract citations/sources if present; Google may return 'citationMetadata' or 'annotations'
            for key in ("citationMetadata", "sources", "citations", "citation", "annotations"):
                if key in resp_json and isinstance(resp_json[key], list):
                    for s in resp_json[key]:
                        if isinstance(s, dict):
                            title = s.get("title") or s.get("name") or ""
                            url = s.get("url") or s.get("link") or s.get("uri") or ""
                            snippet = s.get("snippet") or s.get("excerpt") or s.get("summary") or ""
                            sources.append({"title": title, "url": url, "snippet": snippet})
            # Some responses embed sources under candidates -> tools or content -> metadata
            if "candidates" in resp_json and isinstance(resp_json["candidates"], list):
                for cand in resp_json["candidates"]:
                    if isinstance(cand, dict):
                        cm = cand.get("citationMetadata") or cand.get("citations") or cand.get("sources")
                        if isinstance(cm, list):
                            for s in cm:
                                if isinstance(s, dict):
                                    title = s.get("title") or s.get("name", "") or ""
                                    url = s.get("url") or s.get("link") or ""
                                    snippet = s.get("snippet") or s.get("excerpt") or ""
                                    sources.append({"title": title, "url": url, "snippet": snippet})

    except Exception as e:
        if logger:
            logger.debug(f"Error extracting text/sources from Google response: {e}")

    # Final fallback: if we collected nothing, stringify the full response (no hard cap)
    if not text_parts:
        try:
            text = json.dumps(resp_json, ensure_ascii=False)
        except Exception:
            text = str(resp_json)
    else:
        # Join all discovered parts with double-newline to preserve structure
        text = "\n\n".join([p.strip() for p in text_parts if p and p.strip()])

    return text, sources


def _choose_auth_headers(provider_conf, logger=None) -> Tuple[dict, dict]:
    """
    Choose authentication method for Google API: ADC or API key.
    Returns (headers_dict, params_dict).
    Raises RuntimeError if no valid credentials found.
    """
    logger = logger or logging.getLogger("gpt_processor.google_adapter")
    headers = {}
    params = {}
    api_key = getattr(provider_conf, "api_key", "").strip() or os.getenv("GOOGLE_API_KEY", "").strip()

    if _HAS_GOOGLE_AUTH:
        try:
            credentials, _ = google.auth.default()
            if credentials and credentials.token:
                headers["Authorization"] = f"Bearer {credentials.token}"
                if logger:
                    logger.debug("Using Google Application Default Credentials (ADC) for authentication.")
                return headers, params
            else:
                if logger:
                    logger.debug("ADC token not found, trying API key.")
        except Exception as e:
            if logger:
                logger.debug(f"Failed to get ADC: {e}, trying API key.")

    if api_key:
        params["key"] = api_key
        if logger:
            logger.debug("Using API key for authentication.")
        return headers, params
    
    raise RuntimeError("No valid Google credentials found. Set GOOGLE_API_KEY or configure ADC.")


def _choose_auth_headers(provider_conf, logger=None) -> Tuple[dict, dict]:
    """
    Choose authentication method for Google API: ADC or API key.
    Returns (headers_dict, params_dict).
    Raises RuntimeError if no valid credentials found.
    """
    logger = logger or logging.getLogger("gpt_processor.google_adapter")
    headers = {}
    params = {}
    api_key = getattr(provider_conf, "api_key", "").strip() or os.getenv("GOOGLE_API_KEY", "").strip()

    if _HAS_GOOGLE_AUTH:
        try:
            credentials, _ = google.auth.default()
            if credentials and credentials.token:
                headers["Authorization"] = f"Bearer {credentials.token}"
                if logger:
                    logger.debug("Using Google Application Default Credentials (ADC) for authentication.")
                return headers, params
            else:
                if logger:
                    logger.debug("ADC token not found, trying API key.")
        except Exception as e:
            if logger:
                logger.debug(f"Failed to get ADC: {e}, trying API key.")

    if api_key:
        params["key"] = api_key
        if logger:
            logger.debug("Using API key for authentication.")
        return headers, params
    
    raise RuntimeError("No valid Google credentials found. Set GOOGLE_API_KEY or configure ADC.")


def perform_google_grounding(provider_conf, system_prompt, user_prompt, grounding_options, logger=None):
    """
    Perform provider-side grounding using Google Gemini / Generative API.

    provider_conf: object with .api_key, .model attributes (Config.ProviderConfig or similar)
    grounding_options: dict with possible fields: max_results, search_prompt, temperature, max_tokens
    """
    logger = logger or logging.getLogger("gpt_processor.google_adapter")

    if requests is None:
        raise RuntimeError("The 'requests' package is required for google_adapter. Please install it (pip install requests).")

    api_key = getattr(provider_conf, "api_key", None) or os.getenv("GOOGLE_API_KEY", None)
    model = grounding_options.get("model") or getattr(provider_conf, "model", None)
    if not model:
        raise RuntimeError("No model specified for Google grounding call. Set provider_conf.model or pass grounding_options['model'].")

    # Determine auth headers / params
    try:
        h, p = _choose_auth_headers(provider_conf, logger=logger)
        headers = h
        params = p
    except Exception as e:
        raise RuntimeError(f"Authentication for Google grounding failed: {e}")

    # Build endpoint URL: use the Google Generative API generateContent endpoint.
    base = "https://generativelanguage.googleapis.com"
    endpoint = f"{base}/v1/models/{model}:generateContent"

    # Construct request body using the Generative API 'contents' + 'generationConfig' shape.
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": f"{system_prompt}\n\n{user_prompt}"}
                ]
            }
        ],
        "generationConfig": {
            "maxOutputTokens": grounding_options.get("max_tokens", getattr(provider_conf, "max_tokens", 1500)),
            "temperature": grounding_options.get("temperature", getattr(provider_conf, "temperature", 0.0))
        }
    }

    attempts = 0
    while True:
        try:
            if logger:
                logger.debug(f"Google grounding request to {endpoint} params={params} payload_keys={list(payload.keys())}")
            resp = requests.post(endpoint, headers=headers, params=params, json=payload, timeout=60)
            resp.raise_for_status()
            resp_json = resp.json()

            # Save raw response for debugging
            try:
                _save_raw_response(resp_json, "google", model, logger=logger)
            except Exception:
                pass

            text, sources = _extract_text_and_sources_from_response(resp_json, logger=logger)
            if logger:
                logger.debug(f"Extracted grounding text length={len(text) if text else 0}, sources={len(sources)}")
            return {
                "text": text,
                "sources": sources,
                "method": "provider-tool",
                "tool_details": {"provider_response": "google_genai", "model": model, "status_code": resp.status_code}
            }
        except Exception as e:
            attempts += 1
            if attempts > 1:
                if logger:
                    logger.exception(f"Google grounding failed after {attempts} attempts: {e}")
                # Return a normalized "unavailable" result instead of raising, so caller can fall back
                return {
                    "text": "",
                    "sources": [],
                    "method": "none",
                    "tool_details": {"error": "provider_grounding_unavailable", "exception": str(e)}
                }
            if logger:
                logger.warning(f"Google grounding attempt failed ({e}), retrying once...")
            time.sleep(1.0)
