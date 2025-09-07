"""
Provider API wrapper and robust extraction helpers for FilePromptForge.

Purpose:
- Centralize provider-specific call logic so callers (e.g. gpt_processor_main) can
  delegate provider selection, payload shaping, and robust response extraction.
- This module is designed to be imported and used by gpt_processor_main in a
  later small, reversible change. It does NOT modify existing callers by itself.

Notes:
- This file intentionally does not perform any live runs on import.
- It expects caller to pass provider_conf objects (with .api_key/.api_base as needed).
- Debug/response saving happens only if debug_dir is provided by the caller.
"""

import json
import os
import time
import logging

# Extraction helpers ----------------------------------------------------------
def _extract_text_from_google_resp(resp):
    """
    Robustly extract and concatenate text from Google GenAI responses.
    Accepts dict-like SDK objects or plain dicts.
    """
    try:
        data = resp if isinstance(resp, dict) else (resp.to_dict() if hasattr(resp, "to_dict") else resp.__dict__)
    except Exception:
        data = resp

    texts = []
    try:
        candidates = data.get("candidates", []) if isinstance(data, dict) else []
        for cand in candidates:
            if not isinstance(cand, dict):
                continue
            content = cand.get("content", {}) if isinstance(cand, dict) else {}
            parts = content.get("parts", []) if isinstance(content, dict) else []
            for part in parts:
                if isinstance(part, dict):
                    txt = part.get("text") or part.get("content") or ""
                    if isinstance(txt, list):
                        for t in txt:
                            texts.append(str(t))
                    else:
                        texts.append(str(txt))
                elif isinstance(part, str):
                    texts.append(part)
    except Exception:
        # silent; fallback below
        pass

    if texts:
        return "\n\n".join([t.strip() for t in texts if t and t.strip()])

    # Fallback: try to stringify some useful fields
    try:
        if isinstance(data, dict):
            # try common places
            if "output" in data and isinstance(data["output"], str):
                return data["output"].strip()
            if "response" in data and isinstance(data["response"], dict) and "text" in data["response"]:
                return str(data["response"]["text"]).strip()
        return json.dumps(data, ensure_ascii=False)
    except Exception:
        return str(data)


def _extract_text_from_openai_resp(resp):
    """
    Robustly extract text from various OpenAI SDK response shapes (Responses API or old chat/completions).
    """
    # Try SDK attribute forms
    try:
        if hasattr(resp, "output_text"):
            return resp.output_text.strip()
    except Exception:
        pass

    try:
        if isinstance(resp, dict):
            # Responses API: 'output' array containing content items
            out = resp.get("output")
            if isinstance(out, list) and len(out) > 0:
                for item in out:
                    if isinstance(item, dict):
                        content = item.get("content")
                        if isinstance(content, list):
                            for c in content:
                                if isinstance(c, dict) and c.get("type") in ("output_text", "text"):
                                    return c.get("text", "").strip()
                # Fallback to first element stringification
                try:
                    return str(out[0])
                except Exception:
                    pass
            # Older chat shape
            if "choices" in resp and isinstance(resp["choices"], list) and len(resp["choices"]) > 0:
                ch = resp["choices"][0]
                if isinstance(ch, dict):
                    msg = ch.get("message") or {}
                    if isinstance(msg, dict):
                        content = msg.get("content")
                        if isinstance(content, str):
                            return content.strip()
        # SDK object with choices
        if hasattr(resp, "choices"):
            try:
                choice = resp.choices[0]
                if hasattr(choice, "message") and hasattr(choice.message, "content"):
                    return choice.message.content.strip()
            except Exception:
                pass
    except Exception:
        pass

    # Last resort
    try:
        return str(resp).strip()
    except Exception:
        return ""


# Provider call wrapper -------------------------------------------------------
def _call_provider_api(provider, provider_conf, model, messages_or_contents, kwargs, logger=None, debug_dir=None):
    """
    Centralized provider call helper.

    Args:
      provider: 'google'|'openai'|'openrouter' etc.
      provider_conf: object with attributes (api_key, api_base, model, temperature, ...)
      model: model string
      messages_or_contents: messages list for OpenAI or contents structure for Google
      kwargs: dict of params prepared by caller (must match expected names for the provider client)
      logger: optional logger
      debug_dir: optional path to save raw response JSON for debugging

    Returns:
      text (str), raw_response (object or dict), usage (dict)
    Raises:
      re-raises any client exceptions to let caller decide on fallback behavior.
    """
    logger = logger or logging.getLogger("provider_api")
    p = provider.lower()

    # GOOGLE: prefer google.genai SDK
    if p == "google":
        try:
            from google import genai
        except Exception as e:
            raise RuntimeError(f"google.genai SDK not available: {e}")

        client = genai.Client()
        # Build generation config object (dict) from any known token kwargs
        generation_config = {}
        for k in ("maxOutputTokens", "max_output_tokens"):
            if k in kwargs:
                generation_config["maxOutputTokens"] = kwargs.pop(k)
                break
        if "temperature" in kwargs:
            generation_config["temperature"] = kwargs.pop("temperature")
        contents = messages_or_contents
        resp = client.models.generate_content(model=model, contents=contents, config=generation_config)
        # Save raw response if requested
        if debug_dir:
            try:
                os.makedirs(debug_dir, exist_ok=True)
                path = os.path.join(debug_dir, f"google_raw_{model}_{int(time.time())}.json")
                with open(path, "w", encoding="utf-8") as f:
                    raw = resp if isinstance(resp, dict) else (resp.to_dict() if hasattr(resp, "to_dict") else {})
                    json.dump(raw, f, ensure_ascii=False, indent=2)
                if logger:
                    logger.debug(f"Saved google raw response to {path}")
            except Exception:
                if logger:
                    logger.debug("Failed to save google raw response")
        text = _extract_text_from_google_resp(resp)
        usage = {}
        try:
            usage = resp.get("usageMetadata") if isinstance(resp, dict) else (resp.usage.to_dict() if hasattr(resp, "usage") else {})
        except Exception:
            usage = {}
        return text, resp, usage

    # OPENAI: use OpenAI SDK
    if p == "openai":
        try:
            from openai import OpenAI
        except Exception as e:
            raise RuntimeError(f"OpenAI SDK not available: {e}")

        client = OpenAI(api_key=getattr(provider_conf, "api_key", None), base_url=getattr(provider_conf, "api_base", None))
        resp = client.chat.completions.create(**kwargs)
        if debug_dir:
            try:
                os.makedirs(debug_dir, exist_ok=True)
                path = os.path.join(debug_dir, f"openai_raw_{model}_{int(time.time())}.json")
                raw = resp if isinstance(resp, dict) else (resp.to_dict() if hasattr(resp, "to_dict") else {})
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(raw, f, ensure_ascii=False, indent=2)
                if logger:
                    logger.debug(f"Saved openai raw response to {path}")
            except Exception:
                if logger:
                    logger.debug("Failed to save openai raw response")
        text = _extract_text_from_openai_resp(resp)
        usage = {}
        try:
            usage = resp.usage.to_dict() if hasattr(resp, "usage") else (resp.get("usage") if isinstance(resp, dict) else {})
        except Exception:
            usage = {}
        return text, resp, usage

    # Other providers: not implemented here; caller should handle or extend
    raise NotImplementedError(f"Provider '{provider}' not implemented in provider_api._call_provider_api()")
