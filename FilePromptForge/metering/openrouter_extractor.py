"""
Metering extraction for OpenRouter API responses.

Extracts ALL usage data from OpenRouter responses including:
- Basic tokens (prompt_tokens, completion_tokens — OpenAI-compatible format)
- Reasoning tokens (completion_tokens_details.reasoning_tokens)
- Cached tokens (prompt_tokens_details.cached_tokens)
- Web search usage (server_tool_use.web_search_requests)
- **Authoritative cost** field (usage.cost) — the actual amount charged by OpenRouter

OpenRouter response shape (from /chat/completions):
{
    "usage": {
        "prompt_tokens": 1205,
        "completion_tokens": 487,
        "total_tokens": 1692,
        "prompt_tokens_details": {
            "cached_tokens": 0,
            "cache_write_tokens": 0,
            "audio_tokens": 0,
            "video_tokens": 0
        },
        "completion_tokens_details": {
            "reasoning_tokens": 0,
            "image_tokens": 0
        },
        "cost": 0.00247,
        "is_byok": false,
        "cost_details": {
            "upstream_inference_prompt_cost": 0.0012,
            "upstream_inference_completions_cost": 0.00127
        },
        "server_tool_use": {
            "web_search_requests": 2
        }
    }
}

CRITICAL: The ``usage.cost`` field is the AUTHORITATIVE total cost charged by
OpenRouter. When available, it should be used directly rather than calculating
from per-token rates, as it accounts for provider-specific pricing, search fees,
and plugin costs that may be difficult to replicate.

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
    LOG.debug("[METERING-OPENROUTER] ENTER %s with: %s", func_name, kwargs)

def _log_exit(func_name: str, result: Any) -> None:
    """Log function exit with result."""
    LOG.debug("[METERING-OPENROUTER] EXIT %s returning: %s", func_name, result)

def _log_step(func_name: str, step: str, value: Any = None) -> None:
    """Log intermediate step within a function."""
    LOG.debug("[METERING-OPENROUTER] %s | %s: %s", func_name, step, value)

# Quantize to 6 decimal places
DECIMAL_PLACES = Decimal("0.000001")


def _quantize(value: float) -> Decimal:
    """Convert float to Decimal with exactly 6 decimal places."""
    result = Decimal(str(value)).quantize(DECIMAL_PLACES, rounding=ROUND_HALF_UP)
    LOG.debug("[METERING-OPENROUTER] _quantize: %s -> %s", value, result)
    return result


def _safe_int(value: Any, default: int = 0) -> int:
    """Safely convert to int."""
    if value is None:
        LOG.debug("[METERING-OPENROUTER] _safe_int: None -> default=%d", default)
        return default
    try:
        result = int(value)
        LOG.debug("[METERING-OPENROUTER] _safe_int: %s -> %d", value, result)
        return result
    except (TypeError, ValueError) as e:
        LOG.debug("[METERING-OPENROUTER] _safe_int: %s failed (%s) -> default=%d", value, e, default)
        return default


class OpenRouterMeteringExtractor:
    """
    Extracts metering data from OpenRouter API responses.

    OpenRouter uses OpenAI-compatible chat completions format with additional
    fields for cost tracking. The key advantage is the authoritative ``cost``
    field that represents the actual amount charged.

    Supports:
    - Standard chat completions tokens (prompt_tokens, completion_tokens)
    - Provider-specific token details (reasoning, cached, audio, video, image)
    - Authoritative cost field (usage.cost)
    - Cost breakdown (cost_details.upstream_inference_prompt_cost, etc.)
    - Web search usage (server_tool_use.web_search_requests)
    - Perplexity-specific fields (citation_tokens, search_queries)

    Usage:
        extractor = OpenRouterMeteringExtractor(response_json, model="google/gemini-2.5-flash")
        metering = extractor.extract()
    """

    def __init__(self, response: Dict[str, Any], model: str = "unknown"):
        _log_entry("OpenRouterMeteringExtractor.__init__", model=model, response_keys=list((response or {}).keys()))

        self.response = response or {}
        self.model = model
        self._usage = response.get("usage") or {}
        self._choices = response.get("choices") or []

        LOG.info(
            "[METERING-OPENROUTER] Initialized extractor for model=%s, has_usage=%s, choices=%d",
            model, bool(self._usage), len(self._choices),
        )
        _log_step("__init__", "usage_keys", list(self._usage.keys()))

    def extract_tokens(self) -> Dict[str, Any]:
        """
        Extract all token counts from OpenRouter response.

        Uses OpenAI-compatible Chat Completions format:
        - usage.prompt_tokens (or usage.input_tokens)
        - usage.completion_tokens (or usage.output_tokens)
        - usage.total_tokens

        Provider-specific details:
        - prompt_tokens_details: cached_tokens, cache_write_tokens, audio_tokens, video_tokens
        - completion_tokens_details: reasoning_tokens, image_tokens

        Returns dict with:
        - input: prompt_tokens
        - output: completion_tokens
        - total: total_tokens
        - provider_specific:
            - reasoning_tokens
            - cached_tokens
            - cache_write_tokens
            - audio_tokens
            - video_tokens
            - image_tokens
        """
        _log_entry("extract_tokens", usage=self._usage)

        u = self._usage

        # Primary: Chat Completions format
        input_tokens = _safe_int(u.get("prompt_tokens"))
        output_tokens = _safe_int(u.get("completion_tokens"))
        total_tokens = _safe_int(u.get("total_tokens"))

        # Fallback: Responses API format (some models may use this)
        if input_tokens == 0:
            input_tokens = _safe_int(u.get("input_tokens"))
            _log_step("extract_tokens", "fallback_input_tokens", input_tokens)
        if output_tokens == 0:
            output_tokens = _safe_int(u.get("output_tokens"))
            _log_step("extract_tokens", "fallback_output_tokens", output_tokens)

        # Calculate total if not provided
        if total_tokens == 0 and (input_tokens > 0 or output_tokens > 0):
            total_tokens = input_tokens + output_tokens
            _log_step("extract_tokens", "calculated_total", total_tokens)

        _log_step("extract_tokens", "basic_tokens",
                  {"input": input_tokens, "output": output_tokens, "total": total_tokens})

        # Provider-specific breakdowns
        prompt_details = u.get("prompt_tokens_details") or {}
        completion_details = u.get("completion_tokens_details") or {}

        reasoning_tokens = _safe_int(completion_details.get("reasoning_tokens"))
        cached_tokens = _safe_int(prompt_details.get("cached_tokens"))
        cache_write_tokens = _safe_int(prompt_details.get("cache_write_tokens"))
        audio_tokens = _safe_int(prompt_details.get("audio_tokens"))
        video_tokens = _safe_int(prompt_details.get("video_tokens"))
        image_tokens = _safe_int(completion_details.get("image_tokens"))

        LOG.info(
            "[METERING-OPENROUTER] Token counts: input=%d, output=%d, total=%d, "
            "reasoning=%d, cached=%d, cache_write=%d, audio=%d, video=%d, image=%d",
            input_tokens, output_tokens, total_tokens,
            reasoning_tokens, cached_tokens, cache_write_tokens,
            audio_tokens, video_tokens, image_tokens,
        )

        result = {
            "input": input_tokens,
            "output": output_tokens,
            "total": total_tokens,
            "provider_specific": {
                "reasoning_tokens": reasoning_tokens,
                "cached_tokens": cached_tokens,
                "cache_write_tokens": cache_write_tokens,
                "audio_tokens": audio_tokens,
                "video_tokens": video_tokens,
                "image_tokens": image_tokens,
            },
        }

        _log_exit("extract_tokens", result)
        return result

    def extract_authoritative_cost(self) -> Dict[str, Any]:
        """
        Extract the authoritative cost from OpenRouter's usage.cost field.

        This is the ACTUAL cost charged by OpenRouter and includes:
        - Token costs (input + output)
        - Web search plugin fees
        - Provider-specific surcharges
        - Any other platform fees

        Returns dict with:
        - available: whether usage.cost was present
        - total_cost_usd: the authoritative total cost (Decimal, 6 places)
        - is_byok: whether this was a bring-your-own-key call
        - upstream_prompt_cost: provider's input cost breakdown
        - upstream_completion_cost: provider's output cost breakdown
        """
        _log_entry("extract_authoritative_cost", usage_keys=list(self._usage.keys()))

        cost_raw = self._usage.get("cost")
        is_byok = self._usage.get("is_byok", False)
        cost_details = self._usage.get("cost_details") or {}

        available = cost_raw is not None and isinstance(cost_raw, (int, float))

        if available:
            total_cost = _quantize(float(cost_raw))
            LOG.info(
                "[METERING-OPENROUTER] Authoritative cost from OpenRouter: $%s (is_byok=%s)",
                total_cost, is_byok,
            )
        else:
            total_cost = None
            LOG.warning("[METERING-OPENROUTER] No authoritative cost field in response — will fall back to token-based calculation")

        upstream_prompt_cost = cost_details.get("upstream_inference_prompt_cost")
        upstream_completion_cost = cost_details.get("upstream_inference_completions_cost")

        if upstream_prompt_cost is not None:
            upstream_prompt_cost = _quantize(float(upstream_prompt_cost))
        if upstream_completion_cost is not None:
            upstream_completion_cost = _quantize(float(upstream_completion_cost))

        result = {
            "available": available,
            "total_cost_usd": total_cost,
            "is_byok": is_byok,
            "upstream_prompt_cost": upstream_prompt_cost,
            "upstream_completion_cost": upstream_completion_cost,
        }

        _log_exit("extract_authoritative_cost", result)
        return result

    def extract_web_search(self) -> Dict[str, Any]:
        """
        Extract web search usage from OpenRouter response.

        OpenRouter supports two search engines:
        1. Native: passes through to provider (OpenAI, Anthropic, Perplexity, xAI)
        2. Exa: $4/1,000 results, default for other models

        Web search usage reported in:
            usage.server_tool_use.web_search_requests

        The cost for web search is already included in the authoritative
        ``usage.cost`` field.

        Returns dict with:
        - used: whether web search was invoked
        - provider_tool: "openrouter_web_search"
        - query_count: number of web search requests
        - tool_call_count: same as query_count
        - billable_unit: "included_in_cost" (already in usage.cost)
        """
        _log_entry("extract_web_search", usage_keys=list(self._usage.keys()))

        server_tool_use = self._usage.get("server_tool_use") or {}
        web_search_requests = _safe_int(server_tool_use.get("web_search_requests"))

        used = web_search_requests > 0

        LOG.info(
            "[METERING-OPENROUTER] Web search: used=%s, requests=%d",
            used, web_search_requests,
        )

        result = {
            "used": used,
            "provider_tool": "openrouter_web_search",
            "billable_unit": "included_in_cost",
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
            "provider": "openrouter",
            "usage": self._usage,
            "model": self.response.get("model"),
            "id": self.response.get("id"),
            "system_fingerprint": self.response.get("system_fingerprint"),
        }

        LOG.debug(
            "[METERING-OPENROUTER] Raw usage captured: usage_keys=%s, model=%s, id=%s",
            list(self._usage.keys()),
            self.response.get("model"),
            self.response.get("id"),
        )

        _log_exit("extract_raw_usage", {"keys": list(result.keys())})
        return result

    def extract(self) -> Dict[str, Any]:
        """
        Extract complete metering data.

        Returns a dict ready to be consumed by MeteringEventBuilder.
        Includes the authoritative cost when available.
        """
        _log_entry("extract", model=self.model)

        LOG.info("[METERING-OPENROUTER] ========== Starting full extraction for model=%s ==========", self.model)

        tokens = self.extract_tokens()
        authoritative_cost = self.extract_authoritative_cost()
        web_search = self.extract_web_search()
        raw_usage = self.extract_raw_usage()

        result = {
            "provider": "openrouter",
            "model": self.model,
            "tokens": tokens,
            "tools": {
                "web_search": web_search,
            },
            "authoritative_cost": authoritative_cost,
            "raw_usage": raw_usage,
        }

        LOG.info(
            "[METERING-OPENROUTER] ========== Extraction complete: input=%d, output=%d, "
            "authoritative_cost=%s, web_search_used=%s ==========",
            tokens.get("input", 0),
            tokens.get("output", 0),
            authoritative_cost.get("total_cost_usd"),
            web_search.get("used", False),
        )

        _log_exit("extract", {"provider": "openrouter", "model": self.model, "total_tokens": tokens.get("total", 0)})
        return result


def extract_openrouter_metering(
    response: Dict[str, Any],
    model: str = "unknown",
) -> Dict[str, Any]:
    """
    Convenience function to extract OpenRouter metering.

    Args:
        response: Raw OpenRouter API response JSON
        model: Model name (e.g., "google/gemini-2.5-flash")

    Returns:
        Dict with tokens, tools, authoritative_cost, raw_usage ready for MeteringEvent
    """
    LOG.info(
        "[METERING-OPENROUTER] >>>>>>> extract_openrouter_metering called: model=%s, response_size=%d bytes",
        model, len(json.dumps(response or {})),
    )

    try:
        extractor = OpenRouterMeteringExtractor(response, model)
        result = extractor.extract()
        LOG.info(
            "[METERING-OPENROUTER] <<<<<<< extract_openrouter_metering returning: "
            "total_tokens=%d, authoritative_cost=%s, web_search_used=%s",
            result.get("tokens", {}).get("total", 0),
            result.get("authoritative_cost", {}).get("total_cost_usd"),
            result.get("tools", {}).get("web_search", {}).get("used", False),
        )
        return result
    except Exception as e:
        LOG.error(
            "[METERING-OPENROUTER] !!!!!!! extract_openrouter_metering FAILED: %s\n%s",
            e, traceback.format_exc(),
        )
        # Return minimal data so metering doesn't break execution
        return {
            "provider": "openrouter",
            "model": model,
            "tokens": {"input": 0, "output": 0, "total": 0},
            "tools": {},
            "authoritative_cost": {"available": False, "total_cost_usd": None},
            "raw_usage": {"provider": "openrouter", "extraction_error": str(e)},
        }


# Export
__all__ = [
    "OpenRouterMeteringExtractor",
    "extract_openrouter_metering",
]
