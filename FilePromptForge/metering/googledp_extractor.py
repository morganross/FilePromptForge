"""
Metering extraction for Google Deep Research (Interactions API) responses.

The Interactions API returns a different response shape than generateContent:
- Uses ``usage`` dict (not ``usageMetadata``)
- Field names: total_input_tokens, total_output_tokens, total_thought_tokens,
  total_tool_use_tokens, total_cached_tokens, total_tokens
- No ``candidates[]`` — uses ``outputs[]``
- No ``groundingMetadata`` — Deep Research uses Google Search internally
  but the API doesn't expose per-query search metadata

Pricing: Charged at Gemini 3 Pro rates for all tokens.
Search surcharge: $14/1,000 queries after 5,000 free/month.
Since the API doesn't report query count, we estimate at 160 queries per task
(upper bound from Google's docs for complex research).
"""
from __future__ import annotations

import json
import logging
import traceback
from typing import Any, Dict, Optional

LOG = logging.getLogger(__name__)

# Estimated search queries per Deep Research task.
# Google docs say: standard ~80, complex ~160. We use 160 (upper bound).
ESTIMATED_SEARCH_QUERIES_PER_TASK = 160


class GoogleDPMeteringExtractor:
    """
    Extracts metering data from Google Deep Research (Interactions API) responses.

    Usage:
        extractor = GoogleDPMeteringExtractor(response_json, model)
        metering = extractor.extract()
    """

    def __init__(self, response: Dict[str, Any], model: str = "unknown"):
        self.response = response or {}
        self.model = model
        self._usage = response.get("usage") or {}

        LOG.info(
            "[METERING-GOOGLEDP] Initialized extractor for model=%s, usage_keys=%s",
            model,
            list(self._usage.keys()),
        )

    def extract_tokens(self) -> Dict[str, Any]:
        """
        Extract token counts from the Interactions API ``usage`` dict.

        Maps Interactions API fields to the standard metering schema:
        - total_input_tokens  → input
        - total_output_tokens → output
        - total_tokens        → total
        - total_thought_tokens    → provider_specific.thoughts_tokens
        - total_tool_use_tokens   → provider_specific.tool_use_prompt_tokens
        - total_cached_tokens     → provider_specific.cached_tokens
        """
        u = self._usage

        input_tokens = self._safe_int(u.get("total_input_tokens"))
        output_tokens = self._safe_int(u.get("total_output_tokens"))
        total_tokens = self._safe_int(u.get("total_tokens"))
        thought_tokens = self._safe_int(u.get("total_thought_tokens"))
        tool_use_tokens = self._safe_int(u.get("total_tool_use_tokens"))
        cached_tokens = self._safe_int(u.get("total_cached_tokens"))

        # Handle modality-based input tokens if present
        if input_tokens == 0:
            modalities = u.get("input_tokens_by_modality")
            if isinstance(modalities, list):
                for m in modalities:
                    if isinstance(m, dict):
                        input_tokens += self._safe_int(m.get("tokens"))

        LOG.info(
            "[METERING-GOOGLEDP] Tokens: input=%d, output=%d, total=%d, "
            "thought=%d, tool_use=%d, cached=%d",
            input_tokens, output_tokens, total_tokens,
            thought_tokens, tool_use_tokens, cached_tokens,
        )

        return {
            "input": input_tokens,
            "output": output_tokens,
            "total": total_tokens,
            "provider_specific": {
                "tool_use_prompt_tokens": tool_use_tokens,
                "thoughts_tokens": thought_tokens,
                "cached_tokens": cached_tokens,
            },
        }

    def extract_grounding(self) -> Dict[str, Any]:
        """
        Estimate grounding / web search usage.

        The Interactions API does NOT return groundingMetadata or query lists.
        Deep Research always uses Google Search internally, so we mark it as
        used and estimate the query count at 160 per task (Google's upper bound
        for complex research).
        """
        estimated_queries = ESTIMATED_SEARCH_QUERIES_PER_TASK

        LOG.info(
            "[METERING-GOOGLEDP] Grounding: always used (Deep Research), "
            "estimated_queries=%d",
            estimated_queries,
        )

        return {
            "used": True,
            "provider_tool": "google_search",
            "billable_unit": "per_query",
            "query_count": estimated_queries,
            "tool_call_count": estimated_queries,
            "queries": [],  # Not available from Interactions API
            "has_grounding_supports": False,
            "estimated": True,
        }

    def extract_raw_usage(self) -> Dict[str, Any]:
        """Return the original usage dict for audit."""
        return {
            "provider": "googledp",
            "usage": self._usage,
            "agent": self.response.get("agent"),
            "status": self.response.get("status"),
            "interaction_id": self.response.get("id"),
            "estimated_search_queries": ESTIMATED_SEARCH_QUERIES_PER_TASK,
        }

    def extract(self) -> Dict[str, Any]:
        """
        Extract complete metering data.

        Returns a dict matching the standard metering schema used by
        ``MeteringEventBuilder``.
        """
        LOG.info(
            "[METERING-GOOGLEDP] ========== Starting extraction for model=%s ==========",
            self.model,
        )

        tokens = self.extract_tokens()
        grounding = self.extract_grounding()
        raw_usage = self.extract_raw_usage()

        result = {
            "provider": "googledp",
            "model": self.model,
            "tokens": tokens,
            "tools": {
                "web_search": grounding,
            },
            "raw_usage": raw_usage,
        }

        LOG.info(
            "[METERING-GOOGLEDP] ========== Extraction complete: "
            "input=%d, output=%d, total=%d, estimated_searches=%d ==========",
            tokens.get("input", 0),
            tokens.get("output", 0),
            tokens.get("total", 0),
            ESTIMATED_SEARCH_QUERIES_PER_TASK,
        )

        return result

    @staticmethod
    def _safe_int(value: Any, default: int = 0) -> int:
        if value is None:
            return default
        try:
            return int(value)
        except (TypeError, ValueError):
            return default


def extract_googledp_metering(
    response: Dict[str, Any],
    model: str = "unknown",
) -> Dict[str, Any]:
    """
    Convenience function to extract Google Deep Research metering.

    Args:
        response: Raw Interactions API response JSON
        model: Model name (e.g. "deep-research-pro-preview-12-2025")

    Returns:
        Dict with tokens, tools, raw_usage ready for MeteringEvent
    """
    LOG.info(
        "[METERING-GOOGLEDP] >>> extract_googledp_metering called: model=%s",
        model,
    )

    try:
        extractor = GoogleDPMeteringExtractor(response, model)
        result = extractor.extract()
        LOG.info(
            "[METERING-GOOGLEDP] <<< extract_googledp_metering returning: "
            "total_tokens=%d",
            result.get("tokens", {}).get("total", 0),
        )
        return result
    except Exception as e:
        LOG.error(
            "[METERING-GOOGLEDP] !!! extract_googledp_metering FAILED: %s\n%s",
            e,
            traceback.format_exc(),
        )
        return {
            "provider": "googledp",
            "model": model,
            "tokens": {"input": 0, "output": 0, "total": 0},
            "tools": {},
            "raw_usage": {"provider": "googledp", "extraction_error": str(e)},
        }
