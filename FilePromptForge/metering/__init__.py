"""
Metering extraction for Gemini API responses.

Extracts ALL usage data from Gemini responses including:
- Basic tokens (prompt, candidates, total)
- Tool use tokens (grounding tool calls)
- Thoughts tokens (reasoning/thinking)
- Grounding metadata (web search queries)

This is NEW code - does not modify existing _std_usage().

PRECISION: All costs calculated to 6 decimal places using Decimal.
LOGGING: EXTREME verbose - logs every operation, all values, all decisions.
"""
from __future__ import annotations

import json
import logging
import traceback
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

LOG = logging.getLogger(__name__)

# ============================================================================
# Logging utilities
# ============================================================================

def _log_entry(func_name: str, **kwargs) -> None:
    """Log function entry with all parameters."""
    LOG.debug("[METERING] ENTER %s with: %s", func_name, kwargs)

def _log_exit(func_name: str, result: Any) -> None:
    """Log function exit with result."""
    LOG.debug("[METERING] EXIT %s returning: %s", func_name, result)

def _log_step(func_name: str, step: str, value: Any = None) -> None:
    """Log intermediate step within a function."""
    LOG.debug("[METERING] %s | %s: %s", func_name, step, value)

# Quantize to 6 decimal places
DECIMAL_PLACES = Decimal("0.000001")


def _quantize(value: float) -> Decimal:
    """Convert float to Decimal with exactly 6 decimal places."""
    result = Decimal(str(value)).quantize(DECIMAL_PLACES, rounding=ROUND_HALF_UP)
    LOG.debug("[METERING] _quantize: %s -> %s", value, result)
    return result


def _safe_int(value: Any, default: int = 0) -> int:
    """Safely convert to int."""
    if value is None:
        LOG.debug("[METERING] _safe_int: None -> default=%d", default)
        return default
    try:
        result = int(value)
        LOG.debug("[METERING] _safe_int: %s -> %d", value, result)
        return result
    except (TypeError, ValueError) as e:
        LOG.debug("[METERING] _safe_int: %s failed (%s) -> default=%d", value, e, default)
        return default


class GeminiMeteringExtractor:
    """
    Extracts metering data from Gemini API responses.
    
    Usage:
        extractor = GeminiMeteringExtractor(response_json)
        metering = extractor.extract()
    """
    
    def __init__(self, response: Dict[str, Any], model: str = "unknown"):
        _log_entry("GeminiMeteringExtractor.__init__", model=model, response_keys=list((response or {}).keys()))
        
        self.response = response or {}
        self.model = model
        self._usage_metadata = response.get("usageMetadata") or {}
        self._candidates = response.get("candidates") or []
        self._grounding_metadata = self._get_grounding_metadata()
        
        LOG.info("[METERING-GEMINI] Initialized extractor for model=%s, has_usage=%s, num_candidates=%d",
                 model, bool(self._usage_metadata), len(self._candidates))
        _log_step("__init__", "usage_metadata_keys", list(self._usage_metadata.keys()))
        _log_step("__init__", "grounding_metadata_keys", list(self._grounding_metadata.keys()))
    
    def _get_grounding_metadata(self) -> Dict[str, Any]:
        """Extract grounding metadata from first candidate."""
        _log_entry("_get_grounding_metadata", num_candidates=len(self._candidates))
        
        if not self._candidates:
            _log_exit("_get_grounding_metadata", {})
            return {}
        
        result = self._candidates[0].get("groundingMetadata") or {}
        _log_exit("_get_grounding_metadata", {"keys": list(result.keys())})
        return result
    
    def extract_tokens(self) -> Dict[str, Any]:
        """
        Extract all token counts from response.
        
        Returns dict with:
        - input_tokens: promptTokenCount
        - output_tokens: candidatesTokenCount
        - total_tokens: totalTokenCount
        - provider_specific:
            - tool_use_prompt_tokens: toolUsePromptTokenCount
            - thoughts_tokens: thoughtsTokenCount
        """
        _log_entry("extract_tokens", usage_metadata=self._usage_metadata)
        
        um = self._usage_metadata
        
        input_tokens = _safe_int(um.get("promptTokenCount"))
        output_tokens = _safe_int(um.get("candidatesTokenCount"))
        total_tokens = _safe_int(um.get("totalTokenCount"))
        tool_use_tokens = _safe_int(um.get("toolUsePromptTokenCount"))
        thoughts_tokens = _safe_int(um.get("thoughtsTokenCount"))
        cached_content_tokens = _safe_int(um.get("cachedContentTokenCount"))
        
        LOG.info("[METERING-GEMINI] Token counts: input=%d, output=%d, total=%d, tool_use=%d, thoughts=%d, cached=%d",
                 input_tokens, output_tokens, total_tokens, tool_use_tokens, thoughts_tokens, cached_content_tokens)
        
        result = {
            "input": input_tokens,
            "output": output_tokens,
            "total": total_tokens,
            "provider_specific": {
                "tool_use_prompt_tokens": tool_use_tokens,
                "thoughts_tokens": thoughts_tokens,
                "cached_tokens": cached_content_tokens,
                # Preserve token details if available
                "prompt_tokens_details": um.get("promptTokensDetails"),
                "tool_use_tokens_details": um.get("toolUsePromptTokensDetails"),
            }
        }
        
        _log_exit("extract_tokens", result)
        return result
    
    def extract_grounding(self) -> Dict[str, Any]:
        """
        Extract grounding/web search usage.
        
        Returns dict with:
        - used: whether grounding was invoked
        - provider_tool: "google_search"
        - query_count: number of web search queries
        - queries: list of query strings (for audit)
        - has_grounding_supports: whether response has grounding supports
        """
        _log_entry("extract_grounding", grounding_metadata_keys=list(self._grounding_metadata.keys()))
        
        gm = self._grounding_metadata
        
        web_search_queries = gm.get("webSearchQueries") or []
        grounding_supports = gm.get("groundingSupports") or []
        billing_unit = self._get_billing_unit()
        
        used = len(web_search_queries) > 0 or len(grounding_supports) > 0
        
        LOG.info("[METERING-GEMINI] Grounding: used=%s, query_count=%d, supports_count=%d, billing_unit=%s",
                 used, len(web_search_queries), len(grounding_supports), billing_unit)
        
        if web_search_queries:
            LOG.debug("[METERING-GEMINI] Web search queries: %s", web_search_queries)
        
        result = {
            "used": used,
            "provider_tool": "google_search",
            "billable_unit": billing_unit,
            "query_count": len(web_search_queries),
            "queries": web_search_queries,  # Kept for audit
            "has_grounding_supports": len(grounding_supports) > 0,
        }
        
        _log_exit("extract_grounding", result)
        return result
    
    def _get_billing_unit(self) -> str:
        """
        Determine billing unit based on model version.
        
        - Gemini 3.x: billed per query executed
        - Gemini 2.5 and older: billed per grounded prompt
        """
        _log_entry("_get_billing_unit", model=self.model)
        
        model_lower = self.model.lower()
        
        # Gemini 3.x family
        if any(x in model_lower for x in ["gemini-3", "gemini3"]):
            result = "per_query"
            LOG.info("[METERING-GEMINI] Model %s detected as Gemini 3.x, billing_unit=%s", self.model, result)
        else:
            result = "per_grounded_prompt"
            LOG.info("[METERING-GEMINI] Model %s detected as Gemini 2.5 or older, billing_unit=%s", self.model, result)
        
        _log_exit("_get_billing_unit", result)
        return result
    
    def calculate_grounding_cost(
        self, 
        grounding_data: Dict[str, Any],
        grounding_per_prompt_price: Optional[Decimal] = None,
        grounding_per_query_price: Optional[Decimal] = None,
    ) -> Decimal:
        """
        Calculate grounding/tool cost based on billing model.
        
        Args:
            grounding_data: Output from extract_grounding()
            grounding_per_prompt_price: Price per grounded prompt (Gemini ≤2.5)
            grounding_per_query_price: Price per query (Gemini 3.x)
            
        Returns:
            Decimal cost with 6 decimal places
        """
        _log_entry("calculate_grounding_cost", 
                   grounding_used=grounding_data.get("used"),
                   billable_unit=grounding_data.get("billable_unit"),
                   query_count=grounding_data.get("query_count"),
                   per_prompt_price=grounding_per_prompt_price,
                   per_query_price=grounding_per_query_price)
        
        if not grounding_data.get("used"):
            result = _quantize(0.0)
            LOG.debug("[METERING-GEMINI] Grounding not used, cost=0")
            _log_exit("calculate_grounding_cost", result)
            return result
        
        billing_unit = grounding_data.get("billable_unit", "per_grounded_prompt")
        
        if billing_unit == "per_query" and grounding_per_query_price:
            # Gemini 3.x: charge per query
            query_count = grounding_data.get("query_count", 0)
            result = _quantize(float(grounding_per_query_price) * query_count)
            LOG.info("[METERING-GEMINI] Grounding cost (per_query): %d queries * $%s = $%s",
                     query_count, grounding_per_query_price, result)
            _log_exit("calculate_grounding_cost", result)
            return result
        
        elif billing_unit == "per_grounded_prompt" and grounding_per_prompt_price:
            # Gemini ≤2.5: charge per grounded prompt (flat fee if grounding used)
            result = _quantize(float(grounding_per_prompt_price))
            LOG.info("[METERING-GEMINI] Grounding cost (per_grounded_prompt): flat fee $%s", result)
            _log_exit("calculate_grounding_cost", result)
            return result
        
        # Unknown pricing - return zero but log warning
        LOG.warning(
            "[METERING-GEMINI] Cannot calculate grounding cost: billing_unit=%s, prices=%s/%s",
            billing_unit, grounding_per_prompt_price, grounding_per_query_price
        )
        result = _quantize(0.0)
        _log_exit("calculate_grounding_cost", result)
        return result
    
    def extract_raw_usage(self) -> Dict[str, Any]:
        """
        Return raw usage data for audit purposes.
        """
        _log_entry("extract_raw_usage", model=self.model)
        
        result = {
            "provider": "google",
            "usage_metadata": self._usage_metadata,
            "grounding_metadata": self._grounding_metadata,
            "model_version": self.response.get("modelVersion"),
        }
        
        LOG.debug("[METERING-GEMINI] Raw usage captured: usage_keys=%s, grounding_keys=%s, model_version=%s",
                  list(self._usage_metadata.keys()),
                  list(self._grounding_metadata.keys()),
                  self.response.get("modelVersion"))
        
        _log_exit("extract_raw_usage", {"keys": list(result.keys())})
        return result
    
    def extract(self) -> Dict[str, Any]:
        """
        Extract complete metering data.
        
        Returns a dict ready to be converted to MeteringEvent.
        """
        _log_entry("extract", model=self.model)
        
        LOG.info("[METERING-GEMINI] ========== Starting full extraction for model=%s ==========", self.model)
        
        tokens = self.extract_tokens()
        grounding = self.extract_grounding()
        raw_usage = self.extract_raw_usage()
        
        result = {
            "provider": "google",
            "model": self.model,
            "tokens": tokens,
            "tools": {
                "web_search": grounding,
            },
            "raw_usage": raw_usage,
        }
        
        LOG.info("[METERING-GEMINI] ========== Extraction complete: input=%d, output=%d, grounding_used=%s ==========",
                 tokens.get("input", 0), tokens.get("output", 0), grounding.get("used", False))
        
        _log_exit("extract", {"provider": "google", "model": self.model, "total_tokens": tokens.get("total", 0)})
        return result


def extract_gemini_metering(
    response: Dict[str, Any],
    model: str = "unknown",
) -> Dict[str, Any]:
    """
    Convenience function to extract Gemini metering.
    
    Args:
        response: Raw Gemini API response JSON
        model: Model name (e.g., "gemini-2.5-flash")
        
    Returns:
        Dict with tokens, tools, raw_usage ready for MeteringEvent
    """
    LOG.info("[METERING-GEMINI] >>>>>>> extract_gemini_metering called: model=%s, response_size=%d bytes",
             model, len(json.dumps(response or {})))
    
    try:
        extractor = GeminiMeteringExtractor(response, model)
        result = extractor.extract()
        LOG.info("[METERING-GEMINI] <<<<<<< extract_gemini_metering returning: total_tokens=%d, grounding_used=%s",
                 result.get("tokens", {}).get("total", 0),
                 result.get("tools", {}).get("web_search", {}).get("used", False))
        return result
    except Exception as e:
        LOG.error("[METERING-GEMINI] !!!!!!! extract_gemini_metering FAILED: %s\n%s", e, traceback.format_exc())
        # Return minimal data so metering doesn't break execution
        return {
            "provider": "google",
            "model": model,
            "tokens": {"input": 0, "output": 0, "total": 0},
            "tools": {},
            "raw_usage": {"provider": "google", "error": str(e)},
        }


# Export - use relative imports
from .openai_extractor import (
    OpenAIMeteringExtractor,
    extract_openai_metering,
)
from .googledp_extractor import (
    GoogleDPMeteringExtractor,
    extract_googledp_metering,
)
from .anthropic_extractor import (
    AnthropicMeteringExtractor,
    extract_anthropic_metering,
)
from .openrouter_extractor import (
    OpenRouterMeteringExtractor,
    extract_openrouter_metering,
)
from .perplexity_extractor import (
    PerplexityMeteringExtractor,
    extract_perplexity_metering,
)
from .event_builder import (
    MeteringEventBuilder,
    build_metering_event,
)

__all__ = [
    "GeminiMeteringExtractor",
    "extract_gemini_metering",
    "OpenAIMeteringExtractor",
    "extract_openai_metering",
    "GoogleDPMeteringExtractor",
    "extract_googledp_metering",
    "AnthropicMeteringExtractor",
    "extract_anthropic_metering",
    "OpenRouterMeteringExtractor",
    "extract_openrouter_metering",
    "PerplexityMeteringExtractor",
    "extract_perplexity_metering",
    "MeteringEventBuilder",
    "build_metering_event",
]
