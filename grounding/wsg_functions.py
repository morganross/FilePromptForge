#!/usr/bin/env python3
"""
Grounding helpers for FilePromptForge.

This module intentionally keeps logic minimal. It provides:
- canonicalize_provider_response(resp, provider, model) -> dict
- build_error_metadata(exc, provider, model) -> dict

No fallbacks are performed anywhere.
"""

from typing import Any, Dict, List
from datetime import datetime


def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _extract_text_from_responses(resp: Any) -> str:
    """
    Best-effort text extraction for OpenAI Responses API objects.
    Keeps this intentionally small:
      1) try resp.output_text
      2) try resp.output (collect any textual content-like fields)
    """
    # 1) Convenience property present in newer SDKs
    try:
        txt = getattr(resp, "output_text", None)
        if isinstance(txt, str) and txt.strip():
            return txt.strip()
    except Exception:
        pass

    # 2) Fallback: scan 'output' structure if present
    try:
        output = getattr(resp, "output", None)
        chunks: List[str] = []
        if output:
            # output can be a list of message-like items, each with 'content'
            for item in output:
                # item.content may be a list (parts), or a string
                content = getattr(item, "content", None)
                if isinstance(content, list):
                    for part in content:
                        # part may be an object with 'text' or a dict
                        if hasattr(part, "text"):
                            t = getattr(part, "text", "") or ""
                            if t:
                                chunks.append(str(t))
                        elif isinstance(part, dict):
                            t = part.get("text") or part.get("content") or ""
                            if t:
                                chunks.append(str(t))
                elif isinstance(content, str):
                    chunks.append(content)
        if chunks:
            return "\n".join(chunks).strip()
    except Exception:
        pass

    return ""


def _extract_text_from_chat(resp: Any) -> str:
    """
    Best-effort text extraction for Chat Completions objects.
    """
    try:
        choices = getattr(resp, "choices", []) or []
        if choices:
            c0 = choices[0]
            msg = getattr(c0, "message", None)
            if msg is not None:
                if hasattr(msg, "content"):
                    content = msg.content or ""
                    return (content or "").strip()
                elif isinstance(msg, dict):
                    content = msg.get("content", "") or ""
                    return (content or "").strip()
            # older fields
            if hasattr(c0, "content"):
                content = getattr(c0, "content") or ""
                return (content or "").strip()
            if hasattr(c0, "text"):
                content = getattr(c0, "text") or ""
                return (content or "").strip()
    except Exception:
        pass
    return ""


def canonicalize_provider_response(resp: Any, provider: str, model: str) -> Dict[str, Any]:
    """
    Return a canonical dict:
    {
      "text": str,
      "provider": provider,
      "model": model,
      "method": "provider-tool",
      "sources": [],          # kept minimal
      "tool_details": {},     # kept minimal
      "timestamp": "...Z"
    }
    """
    text = _extract_text_from_responses(resp)
    if not text:
        # Allow chat completions shape (in case caller still uses chat API)
        text = _extract_text_from_chat(resp)

    return {
        "text": text or "",
        "provider": provider,
        "model": model,
        "method": "provider-tool",
        "sources": [],
        "tool_details": {},
        "timestamp": _now_iso(),
    }


def build_error_metadata(exc: Exception, provider: str, model: str) -> Dict[str, Any]:
    return {
        "error": {
            "type": type(exc).__name__,
            "message": str(exc),
        },
        "provider": provider,
        "model": model,
        "method": "provider-tool",
        "timestamp": _now_iso(),
    }
