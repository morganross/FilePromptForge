"""
openrouter_adapter.py

Adapter to perform provider-side grounding using OpenRouter.

This adapter attempts to call OpenRouter's API via the same OpenAI-compatible client used
elsewhere in the project by specifying a base_url. It will prefer using a `:online` model
slug or supplying a `plugins` argument with id "web" where supported.

Notes:
- OpenRouter's exact API surface may differ; this adapter is defensive and attempts a
  reasonable request shape. Adjust as needed for your OpenRouter client/version.
"""

from openai import OpenAI
import logging
import time
import json

def _extract_text_from_response(response):
    try:
        # Best-effort: many SDKs expose output_text or similar
        text = getattr(response, "output_text", None)
        if text:
            return text.strip()
    except Exception:
        pass
    try:
        if hasattr(response, "choices"):
            choice = response.choices[0]
            if hasattr(choice, "message") and hasattr(choice.message, "content"):
                return choice.message.content.strip()
    except Exception:
        pass
    try:
        return str(response)
    except Exception:
        return ""

def _extract_sources_from_response(response):
    # OpenRouter may forward provider citations in varying shapes; best-effort parse.
    sources = []
    try:
        data = response if isinstance(response, dict) else (response.to_dict() if hasattr(response, "to_dict") else None)
        if data:
            # look for tool outputs or citations
            for key in ("tool_calls", "tool_call", "tools", "citations"):
                if key in data and isinstance(data[key], list):
                    for item in data[key]:
                        if isinstance(item, dict):
                            url = item.get("url") or item.get("link")
                            title = item.get("title") or item.get("name")
                            snippet = item.get("snippet") or item.get("summary") or item.get("text")
                            if url or title:
                                sources.append({"title": title or "", "url": url or "", "snippet": snippet or ""})
    except Exception:
        pass
    return sources


def perform_openrouter_grounding(provider_conf, system_prompt, user_prompt, grounding_options, logger=None):
    """
    Perform a provider-side grounding call against OpenRouter.

    provider_conf: object with .api_key, .model, .temperature, .max_tokens attributes
    grounding_options: dict; supports max_results, search_prompt, temperature, max_tokens
    """
    logger = logger or logging.getLogger("gpt_processor.openrouter_adapter")

    api_key = getattr(provider_conf, "api_key", None)
    if not api_key:
        raise RuntimeError("No OpenRouter API key provided in provider_conf.")

    model = grounding_options.get("model") or getattr(provider_conf, "model", None)
    if not model:
        raise RuntimeError("No model specified for OpenRouter grounding call.")

    # If user didn't include ':online' in model but wishes to use online capability, try appending it
    call_model = model
    if ":online" not in call_model:
        call_model = f"{call_model}:online"

    temperature = grounding_options.get("temperature", getattr(provider_conf, "temperature", 0.0))
    max_tokens = grounding_options.get("max_tokens", getattr(provider_conf, "max_tokens", 1500))

    client = OpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1")

    # Attempt plugin-based request shape if supported
    payload = {
        "model": call_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        # plugin hint for web; OpenRouter may accept this or ignore it.
        "plugins": [{"id": "web", "max_results": grounding_options.get("max_results", 3), "search_prompt": grounding_options.get("search_prompt", "")}],
        "temperature": temperature,
        "max_tokens": max_tokens
    }

    if logger:
        logger.debug(f"OpenRouter grounding payload: model={call_model}, plugins={payload.get('plugins')}")

    attempts = 0
    while True:
        try:
            # Many OpenRouter setups are compatible with chat completions endpoint
            response = client.chat.completions.create(**payload)
            text = _extract_text_from_response(response)
            sources = _extract_sources_from_response(response if isinstance(response, dict) else (response.to_dict() if hasattr(response, "to_dict") else {}))
            return {
                "text": text,
                "sources": sources,
                "method": "provider-tool",
                "tool_details": {"provider_response": "openrouter_chat", "model": call_model}
            }
        except Exception as e:
            attempts += 1
            if attempts > 1:
                if logger:
                    logger.exception(f"OpenRouter grounding failed after {attempts} attempts: {e}")
                raise
            if logger:
                logger.warning(f"OpenRouter grounding attempt failed ({e}), retrying once...")
            time.sleep(1.0)
