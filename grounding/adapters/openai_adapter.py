"""
openai_adapter.py

Adapter to perform provider-side grounding using OpenAI (Responses API / tool-enabled models).

Notes:
- This implementation uses the OpenAI Python client instance `OpenAI(api_key=..., base_url=...)`
  as used elsewhere in the project.
- The code is defensive about response shapes because provider SDKs / responses differ by
  version. It attempts several common patterns to extract the final text and any tool outputs.
- If the provider/model does not actually support the web_search tool, the call will likely
  raise an error which should be handled by the caller (Grounder).
"""

from openai import OpenAI
import logging
import time

def _extract_text_from_response(response):
    """
    Try to pull a human-readable text from a Responses API response object/dict.
    Returns a string.
    """
    # Try attribute used by some SDKs
    try:
        text = getattr(response, "output_text", None)
        if text:
            return text.strip()
    except Exception:
        pass

    # Try dict-like access
    try:
        # Some SDKs return a dict-like object with 'output' array
        out = response.get("output") if isinstance(response, dict) else None
        if out and len(out) > 0:
            # Try to find a text content element
            for item in out:
                # item might be dict with 'content' field
                content = item.get("content") if isinstance(item, dict) else None
                if content and isinstance(content, list):
                    for c in content:
                        if isinstance(c, dict) and c.get("type") == "output_text":
                            return c.get("text", "").strip()
                        if isinstance(c, dict) and c.get("type") == "message":
                            # nested message
                            msg = c.get("message", {})
                            if isinstance(msg, dict):
                                return msg.get("content", "").strip()
            # Fallback: stringify the first element
            try:
                return str(out[0])
            except Exception:
                pass
    except Exception:
        pass

    # Try older chat response shapes (not ideal for responses API, but defensive)
    try:
        if hasattr(response, "choices"):
            choice = response.choices[0]
            if hasattr(choice, "message") and hasattr(choice.message, "content"):
                return choice.message.content.strip()
    except Exception:
        pass

    # Last resort: convert to string
    try:
        return str(response).strip()
    except Exception:
        return ""


def _extract_sources_from_response(response):
    """
    Best-effort extraction of source/citation metadata from provider response.
    Returns a list of {title, url, snippet} dicts. Many provider responses may not include this,
    so an empty list is an expected result.
    """
    sources = []
    try:
        # Responses API may include tool_call outputs or citations in structured fields.
        # Attempt several heuristics.
        data = response if isinstance(response, dict) else None
        if data:
            # toolCalls or tool_call
            for key in ("tool_calls", "tool_call", "tools"):
                if key in data and isinstance(data[key], list):
                    for tc in data[key]:
                        # tc may have 'name' and 'output' fields
                        out = tc.get("output", {})
                        if isinstance(out, dict):
                            # attempt to extract urls from output
                            for k, v in out.items():
                                if isinstance(v, list):
                                    for item in v:
                                        if isinstance(item, dict):
                                            url = item.get("url") or item.get("link")
                                            title = item.get("title") or item.get("name")
                                            snippet = item.get("snippet") or item.get("summary") or item.get("text")
                                            if url or title:
                                                sources.append({"title": title or "", "url": url or "", "snippet": snippet or ""})
        # fallback: look for 'citations' field
        if data and "citations" in data and isinstance(data["citations"], list):
            for c in data["citations"]:
                sources.append({
                    "title": c.get("title", ""),
                    "url": c.get("url", ""),
                    "snippet": c.get("snippet", "") or c.get("excerpt", "")
                })
    except Exception:
        # be silent on parsing errors — return what we have
        pass
    return sources


def perform_openai_grounding(provider_conf, system_prompt, user_prompt, grounding_options, logger=None):
    """
    Call OpenAI Responses API enabling the web_search_preview tool where possible.

    provider_conf: object with .api_key, .model, .temperature, .max_tokens attributes (Config.ProviderConfig)
    grounding_options: dict; supports max_results, search_context_size, search_prompt, temperature, max_tokens
    """
    logger = logger or logging.getLogger("gpt_processor.openai_adapter")

    api_key = getattr(provider_conf, "api_key", None)
    if not api_key:
        raise RuntimeError("No OpenAI API key provided in provider_conf.")

    model = grounding_options.get("model") or getattr(provider_conf, "model", None)
    if not model:
        raise RuntimeError("No model specified for OpenAI grounding call.")

    # Prepare tool options for web search. These fields are examples and may vary by provider API.
    # Use a minimal tools payload compatible with the installed OpenAI SDK / Responses API.
    tools = [
        {
            "type": "web_search_preview",
            "search_context_size": grounding_options.get("search_context_size", "medium")
        }
    ]

    temperature = grounding_options.get("temperature", getattr(provider_conf, "temperature", 0.0))
    max_tokens = grounding_options.get("max_tokens", getattr(provider_conf, "max_tokens", 1500))

    client = OpenAI(api_key=api_key)  # base_url defaults to OpenAI public

    # Build request payload. Responses API accepts 'model' and 'input' (or 'messages'), and 'tools'.
    payload = {
        "model": model,
        "tools": tools,
        "input": user_prompt,
        "temperature": temperature,
        "max_output_tokens": max_tokens
    }
    if logger:
        logger.debug(f"OpenAI grounding payload: model={model}, tools={tools}, temperature={temperature}, max_tokens={max_tokens}")

    # Attempt the call with a single quick retry on transient errors
    attempts = 0
    while True:
        try:
            response = client.responses.create(**payload)
            # Normalize the response
            text = _extract_text_from_response(response)
            sources = _extract_sources_from_response(response if isinstance(response, dict) else (response.to_dict() if hasattr(response, "to_dict") else {}))
            return {
                "text": text,
                "sources": sources,
                "method": "provider-tool",
                "tool_details": {"provider_response": "openai_responses", "model": model}
            }
        except Exception as e:
            attempts += 1
            if attempts > 1:
                # Give up and surface the exception
                if logger:
                    logger.exception(f"OpenAI grounding failed after {attempts} attempts: {e}")
                raise
            # Small backoff then retry once
            if logger:
                logger.warning(f"OpenAI grounding attempt failed ({e}), retrying once...")
            time.sleep(1.0)
