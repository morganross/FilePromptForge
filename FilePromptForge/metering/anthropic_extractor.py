"""
Metering extraction for Anthropic Claude API responses.

Extracts ALL usage data from Anthropic Messages API responses including:
- Basic tokens (input_tokens, output_tokens)
- Cache tokens (cache_read_input_tokens, cache_creation_input_tokens)
- Web search usage (server_tool_use.web_search_requests)

Anthropic Messages API usage response shape:
{
    "usage": {
        "input_tokens": 105,
        "output_tokens": 6039,
        "cache_read_input_tokens": 7123,
        "cache_creation_input_tokens": 7345,
        "server_tool_use": {
            "web_search_requests": 1
        }
    }
}

Web search billing:
- $10 / 1,000 searches ($0.01 per search)
- Search content tokens are billed at model input rate (included in input_tokens)
- Web search tool adds 346 tokens system prompt overhead

PRECISION: All costs calculated to 6 decimal places using Decimal.
LOGGING: EXTREME verbose - logs every operation, all values, all decisions.
"""
from __future__ import annotations

import json
import logging
import traceback
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, Optional

LOG = logging.getLogger(__name__)

# ============================================================================
# Logging utilities
# ============================================================================

def _log_entry(func_name: str, **kwargs) -> None:
    """Log function entry with all parameters."""
    LOG.debug("[METERING-ANTHROPIC] ENTER %s with: %s", func_name, kwargs)

def _log_exit(func_name: str, result: Any) -> None:
    """Log function exit with result."""
    LOG.debug("[METERING-ANTHROPIC] EXIT %s returning: %s", func_name, result)

def _log_step(func_name: str, step: str, value: Any = None) -> None:
    """Log intermediate step within a function."""
    LOG.debug("[METERING-ANTHROPIC] %s | %s: %s", func_name, step, value)

# Quantize to 6 decimal places
DECIMAL_PLACES = Decimal("0.000001")


def _quantize(value: float) -> Decimal:
    """Convert float to Decimal with exactly 6 decimal places."""
    result = Decimal(str(value)).quantize(DECIMAL_PLACES, rounding=ROUND_HALF_UP)
    LOG.debug("[METERING-ANTHROPIC] _quantize: %s -> %s", value, result)
    return result


def _safe_int(value: Any, default: int = 0) -> int:
    """Safely convert to int."""
    if value is None:
        LOG.debug("[METERING-ANTHROPIC] _safe_int: None -> default=%d", default)
        return default
    try:
        result = int(value)
        LOG.debug("[METERING-ANTHROPIC] _safe_int: %s -> %d", value, result)
        return result
    except (TypeError, ValueError) as e:
        LOG.debug("[METERING-ANTHROPIC] _safe_int: %s failed (%s) -> default=%d", value, e, default)
        return default


class AnthropicMeteringExtractor:
    """
    Extracts metering data from Anthropic Messages API responses.

    Supports:
    - Messages API usage fields (input_tokens, output_tokens)
    - Prompt caching (cache_read_input_tokens, cache_creation_input_tokens)
    - Web search tool (server_tool_use.web_search_requests)
    - Extended thinking content blocks (thinking/reasoning tokens)

    Usage:
        extractor = AnthropicMeteringExtractor(response_json)
        metering = extractor.extract()
    """

    def __init__(self, response: Dict[str, Any], model: str = "unknown"):
        _log_entry("AnthropicMeteringExtractor.__init__", model=model, response_keys=list((response or {}).keys()))

        self.response = response or {}
        self.model = model
        self._usage = response.get("usage") or {}
        self._content = response.get("content") or []

        LOG.info(
            "[METERING-ANTHROPIC] Initialized extractor for model=%s, has_usage=%s, content_blocks=%d",
            model, bool(self._usage), len(self._content),
        )
        _log_step("__init__", "usage_keys", list(self._usage.keys()))
        _log_step("__init__", "content_types", [b.get("type") for b in self._content[:10]] if self._content else [])

    def extract_tokens(self) -> Dict[str, Any]:
        """
        Extract all token counts from Anthropic response.

        Anthropic Messages API returns:
        - usage.input_tokens: total input tokens (includes search content tokens)
        - usage.output_tokens: total output tokens
        - usage.cache_read_input_tokens: tokens served from prompt cache (0.1x rate)
        - usage.cache_creation_input_tokens: tokens written to prompt cache (1.25x rate)

        Returns dict with:
        - input: input_tokens
        - output: output_tokens
        - total: input + output
        - provider_specific:
            - cached_tokens: cache_read_input_tokens (for cost calc at reduced rate)
            - cache_creation_tokens: cache_creation_input_tokens
            - reasoning_tokens: estimated from thinking content blocks
        """
        _log_entry("extract_tokens", usage=self._usage)

        u = self._usage

        input_tokens = _safe_int(u.get("input_tokens"))
        output_tokens = _safe_int(u.get("output_tokens"))
        cache_read_tokens = _safe_int(u.get("cache_read_input_tokens"))
        cache_creation_tokens = _safe_int(u.get("cache_creation_input_tokens"))

        # Calculate total
        total_tokens = input_tokens + output_tokens
        _log_step("extract_tokens", "basic_tokens",
                  {"input": input_tokens, "output": output_tokens, "total": total_tokens})

        # Estimate reasoning/thinking tokens from content blocks
        reasoning_tokens = self._estimate_thinking_tokens()

        LOG.info(
            "[METERING-ANTHROPIC] Token counts: input=%d, output=%d, total=%d, "
            "cache_read=%d, cache_creation=%d, reasoning_est=%d",
            input_tokens, output_tokens, total_tokens,
            cache_read_tokens, cache_creation_tokens, reasoning_tokens,
        )

        result = {
            "input": input_tokens,
            "output": output_tokens,
            "total": total_tokens,
            "provider_specific": {
                "cached_tokens": cache_read_tokens,
                "cache_creation_tokens": cache_creation_tokens,
                "reasoning_tokens": reasoning_tokens,
            },
        }

        _log_exit("extract_tokens", result)
        return result

    def _estimate_thinking_tokens(self) -> int:
        """
        Estimate thinking/reasoning tokens from content blocks.

        Anthropic returns thinking as content blocks with type="thinking".
        We can't get exact thinking token counts from the response, but
        we can detect their presence. The output_tokens already includes
        thinking tokens in the billing.
        """
        _log_entry("_estimate_thinking_tokens", content_count=len(self._content))

        thinking_blocks = 0
        for block in self._content:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if btype in ("thinking", "reasoning", "redacted_thinking"):
                thinking_blocks += 1

        if thinking_blocks > 0:
            LOG.info("[METERING-ANTHROPIC] Found %d thinking/reasoning content blocks", thinking_blocks)
        else:
            LOG.debug("[METERING-ANTHROPIC] No thinking content blocks found")

        _log_exit("_estimate_thinking_tokens", 0)
        # Return 0 — Anthropic bills thinking tokens as part of output_tokens,
        # and does not report them separately in usage. We record the presence
        # but don't double-count.
        return 0

    def extract_web_search(self) -> Dict[str, Any]:
        """
        Extract web search tool usage from Anthropic response.

        Anthropic reports web search usage in:
            usage.server_tool_use.web_search_requests

        Billing: $10 / 1,000 searches = $0.01 per search.
        Failed searches are NOT billed.
        Search content tokens are included in input_tokens at model input rate.

        Returns dict with:
        - used: whether web search was invoked
        - provider_tool: "anthropic_web_search"
        - query_count: number of web search requests
        - tool_call_count: same as query_count (each request = 1 billable unit)
        - billable_unit: "per_1k_searches"
        """
        _log_entry("extract_web_search", usage_keys=list(self._usage.keys()))

        server_tool_use = self._usage.get("server_tool_use") or {}
        web_search_requests = _safe_int(server_tool_use.get("web_search_requests"))

        used = web_search_requests > 0

        LOG.info(
            "[METERING-ANTHROPIC] Web search: used=%s, requests=%d, server_tool_use=%s",
            used, web_search_requests, server_tool_use,
        )

        # Also check content blocks for web search tool_use blocks (belt-and-suspenders)
        if not used and self._content:
            for block in self._content:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    tool_name = block.get("name", "")
                    if "web_search" in tool_name.lower():
                        used = True
                        web_search_requests = max(web_search_requests, 1)
                        LOG.info("[METERING-ANTHROPIC] Detected web search from content block tool_use: %s", tool_name)
                        break

        result = {
            "used": used,
            "provider_tool": "anthropic_web_search",
            "billable_unit": "per_1k_searches",
            "query_count": web_search_requests,
            "tool_call_count": web_search_requests,
            "open_page_count": 0,
            "find_in_page_count": 0,
        }

        _log_exit("extract_web_search", result)
        return result

    def extract_raw_usage(self) -> Dict[str, Any]:
        """Return raw usage data for audit purposes."""
        _log_entry("extract_raw_usage", model=self.model)

        result = {
            "provider": "anthropic",
            "usage": self._usage,
            "model": self.response.get("model"),
            "id": self.response.get("id"),
            "type": self.response.get("type"),
            "stop_reason": self.response.get("stop_reason"),
            "content_block_types": [b.get("type") for b in self._content if isinstance(b, dict)],
        }

        LOG.debug(
            "[METERING-ANTHROPIC] Raw usage captured: usage_keys=%s, model=%s, id=%s, stop_reason=%s",
            list(self._usage.keys()),
            self.response.get("model"),
            self.response.get("id"),
            self.response.get("stop_reason"),
        )

        _log_exit("extract_raw_usage", {"keys": list(result.keys())})
        return result

    def extract(self) -> Dict[str, Any]:
        """
        Extract complete metering data.

        Returns a dict ready to be consumed by MeteringEventBuilder.
        """
        _log_entry("extract", model=self.model)

        LOG.info("[METERING-ANTHROPIC] ========== Starting full extraction for model=%s ==========", self.model)

        tokens = self.extract_tokens()
        web_search = self.extract_web_search()
        raw_usage = self.extract_raw_usage()

        result = {
            "provider": "anthropic",
            "model": self.model,
            "tokens": tokens,
            "tools": {
                "web_search": web_search,
            },
            "raw_usage": raw_usage,
        }

        LOG.info(
            "[METERING-ANTHROPIC] ========== Extraction complete: input=%d, output=%d, "
            "web_search_used=%s, web_search_requests=%d ==========",
            tokens.get("input", 0),
            tokens.get("output", 0),
            web_search.get("used", False),
            web_search.get("query_count", 0),
        )

        _log_exit("extract", {"provider": "anthropic", "model": self.model, "total_tokens": tokens.get("total", 0)})
        return result


def extract_anthropic_metering(
    response: Dict[str, Any],
    model: str = "unknown",
) -> Dict[str, Any]:
    """
    Convenience function to extract Anthropic metering.

    Args:
        response: Raw Anthropic Messages API response JSON
        model: Model name (e.g., "claude-sonnet-4-5")

    Returns:
        Dict with tokens, tools, raw_usage ready for MeteringEvent
    """
    LOG.info(
        "[METERING-ANTHROPIC] >>>>>>> extract_anthropic_metering called: model=%s, response_size=%d bytes",
        model, len(json.dumps(response or {})),
    )

    try:
        extractor = AnthropicMeteringExtractor(response, model)
        result = extractor.extract()
        LOG.info(
            "[METERING-ANTHROPIC] <<<<<<< extract_anthropic_metering returning: "
            "total_tokens=%d, web_search_used=%s",
            result.get("tokens", {}).get("total", 0),
            result.get("tools", {}).get("web_search", {}).get("used", False),
        )
        return result
    except Exception as e:
        LOG.error(
            "[METERING-ANTHROPIC] !!!!!!! extract_anthropic_metering FAILED: %s\n%s",
            e, traceback.format_exc(),
        )
        # Return minimal data so metering doesn't break execution
        return {
            "provider": "anthropic",
            "model": model,
            "tokens": {"input": 0, "output": 0, "total": 0},
            "tools": {},
            "raw_usage": {"provider": "anthropic", "extraction_error": str(e)},
        }


# Export
__all__ = [
    "AnthropicMeteringExtractor",
    "extract_anthropic_metering",
]
