#!/usr/bin/env python3
"""
Grounding helpers for FilePromptForge.

Enhancements:
- Aggregate text across multiple possible response shapes (Responses API and Chat Completions).
- Add raw_response_excerpt in metadata to assist debugging (first ~12KB of the provider/proxy object).
- More accurate 'method' labeling: "provider-tool" only if we have evidence of sources/citations; else "no-tool".
  (We keep 'sources' minimal; proxy-specific mappers should populate citations where possible.)

NOTE: This stays provider-agnostic. No provider/model branching here.
"""

from typing import Any, Dict, List
from datetime import datetime

RAW_EXCERPT_LIMIT = 12_000


def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _safe_str(obj: Any, limit: int = RAW_EXCERPT_LIMIT) -> str:
    """
    Best-effort stringification of the SDK/proxy response object without raising.
    Truncates to avoid massive logs.
    """
    try:
        s = str(obj)
    except Exception:
        s = "<unprintable response object>"
    if s is None:
        s = ""
    return s[:limit]


def _collect_text_chunks_from_responses(resp: Any) -> List[str]:
    """
    Best-effort text aggregation for OpenAI Responses API transformed objects.
    We try multiple shapes in order, without returning early, to avoid missing segments.
    """
    chunks: List[str] = []

    # 1) Convenience property present in newer SDKs
    try:
        txt = getattr(resp, "output_text", None)
        if isinstance(txt, str) and txt.strip():
            chunks.append(txt.strip())
    except Exception:
        pass

    # 2) Scan 'output' structure if present
    try:
        output = getattr(resp, "output", None)
        if output:
            for item in output:
                # item.content may be a list (parts), or a string
                content = getattr(item, "content", None)
                if isinstance(content, list):
                    for part in content:
                        # part may be an object with 'text' or a dict
                        if hasattr(part, "text"):
                            t = getattr(part, "text", "") or ""
                            if isinstance(t, str) and t.strip():
                                chunks.append(t.strip())
                        elif isinstance(part, dict):
                            t = part.get("text") or part.get("content") or ""
                            if isinstance(t, str) and t.strip():
                                chunks.append(t.strip())
                elif isinstance(content, str) and content.strip():
                    chunks.append(content.strip())
    except Exception:
        pass

    # 3) Some mappers might expose a top-level 'content' (string) on the response
    try:
        cont = getattr(resp, "content", None)
        if isinstance(cont, str) and cont.strip():
            chunks.append(cont.strip())
    except Exception:
        pass

    return chunks


def _collect_text_chunks_from_chat(resp: Any) -> List[str]:
    """
    Best-effort text aggregation for Chat Completions objects.
    """
    chunks: List[str] = []
    try:
        choices = getattr(resp, "choices", []) or []
        if choices:
            c0 = choices[0]
            msg = getattr(c0, "message", None)
            if msg is not None:
                if hasattr(msg, "content"):
                    content = msg.content or ""
                    if isinstance(content, str) and content.strip():
                        chunks.append(content.strip())
                elif isinstance(msg, dict):
                    content = msg.get("content", "") or ""
                    if isinstance(content, str) and content.strip():
                        chunks.append(content.strip())
            # Older fields
            if hasattr(c0, "content"):
                content = getattr(c0, "content") or ""
                if isinstance(content, str) and content.strip():
                    chunks.append(content.strip())
            if hasattr(c0, "text"):
                content = getattr(c0, "text") or ""
                if isinstance(content, str) and content.strip():
                    chunks.append(content.strip())
    except Exception:
        pass
    return chunks


def _aggregate_text(resp: Any) -> str:
    """
    Aggregate all discovered text chunks from possible response shapes.
    De-duplicate while preserving order.
    """
    chunks: List[str] = []
    seen = set()

    for t in _collect_text_chunks_from_responses(resp):
        if t not in seen:
            chunks.append(t)
            seen.add(t)

    for t in _collect_text_chunks_from_chat(resp):
        if t not in seen:
            chunks.append(t)
            seen.add(t)

    # Join with double newline to maintain separation without fusing sentences.
    return "\n\n".join(chunks).strip()


def _extract_sources(resp: Any) -> List[Dict[str, str]]:
    """
    Placeholder for citations/sources extraction.
    If LiteLLM or provider returns structured citations, map them here.
    For now, keep this minimal and return empty to avoid false claims.
    """
    sources: List[Dict[str, str]] = []
    # Example future parsing (pseudo):
    # try:
    #     tool_output = getattr(resp, "tool_output", None) or {}
    #     cites = tool_output.get("citations", [])
    #     for c in cites:
    #         sources.append({
    #             "title": c.get("title", ""),
    #             "url": c.get("url", ""),
    #             "snippet": c.get("snippet", "")
    #         })
    # except Exception:
    #     pass
    return sources


def canonicalize_provider_response(resp: Any, provider: str, model: str) -> Dict[str, Any]:
    """
    Return a canonical dict:
    {
      "text": str,
      "provider": provider,
      "model": model,
      "method": "provider-tool" | "no-tool",
      "sources": [ {title, url, snippet} ],
      "tool_details": {},
      "raw_response_excerpt": str,
      "timestamp": "...Z"
    }
    """
    text = _aggregate_text(resp)
    sources = _extract_sources(resp)

    # Determine method based on evidence of citations/tool output.
    method = "provider-tool" if (sources and len(sources) > 0) else "no-tool"

    meta = {
        "text": text or "",
        "provider": provider,
        "model": model,
        "method": method,
        "sources": sources,
        "tool_details": {},
        "raw_response_excerpt": _safe_str(resp),
        "timestamp": _now_iso(),
    }
    return meta


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
