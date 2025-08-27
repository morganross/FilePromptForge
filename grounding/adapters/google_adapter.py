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

Notes:
- This adapter requires `requests`. If you prefer the official Google client libraries,
  replace the HTTP calls with google.genai client calls.
- If provider_conf.api_key is not provided and google.auth is unavailable or cannot produce
  credentials, the adapter will raise RuntimeError.
"""

import os
import time
import json
import logging

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


def _choose_auth_headers(provider_conf, logger=None):
    """
    Returns tuple (base_url, headers, params) where:
    - base_url is the endpoint root to call
    - headers is a dict of HTTP headers to set (may include Authorization Bearer)
    - params is a dict of query params to attach (may include 'key' for API key)
    """
    logger = logger or logging.getLogger("gpt_processor.google_adapter")
    api_key = getattr(provider_conf, "api_key", None) or os.getenv("GOOGLE_API_KEY", None)
    headers = {"Content-Type": "application/json"}
    params = {}
    # Prefer google.auth ADC if available and no explicit api_key provided
    if _HAS_GOOGLE_AUTH and not api_key:
        try:
            creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
            # Ensure credentials are valid / refreshed
            auth_req = google.auth.transport.requests.Request()
            creds.refresh(auth_req)
            token = creds.token
            if token:
                headers["Authorization"] = f"Bearer {token}"
                return headers, params
        except Exception as e:
            if logger:
                logger.warning(f"google.auth available but failed to obtain credentials: {e}. Falling back to API key if present.")
            # fall through to API key path
    if api_key:
        # Use API key in query params
        params["key"] = api_key
        return headers, params
    # No auth available
    raise RuntimeError("No Google credentials available: set provider_conf.api_key or configure Application Default Credentials.")


def _extract_text_and_sources_from_response(resp_json, logger=None):
    """
    Try several common response shapes for the Google Generative API and extract:
    - text: the generated assistant text
    - sources: list of {title, url, snippet}
    Returns (text, sources)
    """
    logger = logger or logging.getLogger("gpt_processor.google_adapter")
    text = ""
    sources = []

    try:
        # Newer GenAI responses often have 'candidates' or 'output' or 'content' fields
        # Try common locations
        if isinstance(resp_json, dict):
            # Common pattern: {'candidates': [{'output': '...'}], ...}
            if "candidates" in resp_json and isinstance(resp_json["candidates"], list) and len(resp_json["candidates"]) > 0:
                cand = resp_json["candidates"][0]
                # candidate may have 'output' or 'content'
                if isinstance(cand, dict):
                    if "output" in cand and isinstance(cand["output"], str):
                        text = cand["output"].strip()
                    elif "content" in cand:
                        # content may be string or list
                        if isinstance(cand["content"], str):
                            text = cand["content"].strip()
                        elif isinstance(cand["content"], list) and len(cand["content"]) > 0:
                            # find text-like entry
                            for part in cand["content"]:
                                if isinstance(part, dict) and part.get("type") in ("output_text", "text"):
                                    text = part.get("text", "").strip()
                                    break
            # Another pattern: top-level 'output' with structured content
            if not text and "output" in resp_json:
                out = resp_json["output"]
                if isinstance(out, str):
                    text = out.strip()
                elif isinstance(out, dict):
                    # maybe out -> 'content' -> list of items
                    content = out.get("content")
                    if isinstance(content, str):
                        text = content.strip()
                    elif isinstance(content, list):
                        for part in content:
                            if isinstance(part, dict) and part.get("type") in ("output_text", "text"):
                                text = part.get("text", "").strip()
                                break
            # Legacy pattern: 'response' / 'text'
            if not text and "response" in resp_json and isinstance(resp_json["response"], dict):
                text = resp_json["response"].get("text", "").strip()

            # Extract citations/sources if present; Google may return 'citationMetadata' or 'annotations'
            # Try several heuristics
            #  - resp_json.get('citationMetadata'), resp_json.get('sources'), resp_json.get('citation', [])
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
                        # look for 'citationMetadata' in candidate
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

    # Final fallback: try to convert entire response to string if still empty
    if not text:
        try:
            text = json.dumps(resp_json)[:2000]
        except Exception:
            text = str(resp_json)[:2000]
    return text, sources


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
        headers, params = {}, {}
        # _choose_auth_headers returns (headers, params) via raising or returning dicts
        h, p = _choose_auth_headers(provider_conf, logger=logger)
        headers.update(h)
        params.update(p)
    except Exception as e:
        raise RuntimeError(f"Authentication for Google grounding failed: {e}")

    # Build endpoint URL: use the Google Generative API generateContent endpoint.
    # Many public examples use this path: https://generativelanguage.googleapis.com/v1/models/{model}:generateContent
    # If your account uses a different API version (v1beta2), adjust accordingly.
    base = "https://generativelanguage.googleapis.com"
    endpoint = f"{base}/v1/models/{model}:generateContent"
    # If API key provided via params, requests will attach it as ?key=API_KEY

    # Construct request body using the Generative API 'contents' + 'generationConfig' shape.
    # This format is compatible with the public Gemini/Generative API examples.
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

    # Some GenAI endpoints expect 'input' instead of 'prompt'; try with 'prompt' first.
    attempts = 0
    while True:
        try:
            if logger:
                logger.debug(f"Google grounding request to {endpoint} params={params} payload_keys={list(payload.keys())}")
            resp = requests.post(endpoint, headers=headers, params=params, json=payload, timeout=30)
            # Raise for HTTP errors
            resp.raise_for_status()
            resp_json = resp.json()
            text, sources = _extract_text_and_sources_from_response(resp_json, logger=logger)
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
