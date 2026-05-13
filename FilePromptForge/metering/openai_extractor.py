"""
Metering extraction for OpenAI API responses.

Extracts ALL usage data from OpenAI responses including:
- Basic tokens (input, output, total)
- Reasoning tokens (for o1/o3 models)
- Cached tokens
- Web search tool usage (search, open_page, find_in_page actions)

This is NEW code - does not modify existing _std_usage().

PRECISION: All costs calculated to 6 decimal places using Decimal.
LOGGING: EXTREME verbose - logs every operation, all values, all decisions.
"""
from __future__ import annotations

import json
import logging
import traceback
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional

LOG = logging.getLogger(__name__)

# ============================================================================
# Logging utilities
# ============================================================================

def _log_entry(func_name: str, **kwargs) -> None:
    """Log function entry with all parameters."""
    LOG.debug("[METERING-OPENAI] ENTER %s with: %s", func_name, kwargs)

def _log_exit(func_name: str, result: Any) -> None:
    """Log function exit with result."""
    LOG.debug("[METERING-OPENAI] EXIT %s returning: %s", func_name, result)

def _log_step(func_name: str, step: str, value: Any = None) -> None:
    """Log intermediate step within a function."""
    LOG.debug("[METERING-OPENAI] %s | %s: %s", func_name, step, value)

# Quantize to 6 decimal places
DECIMAL_PLACES = Decimal("0.000001")


def _quantize(value: float) -> Decimal:
    """Convert float to Decimal with exactly 6 decimal places."""
    result = Decimal(str(value)).quantize(DECIMAL_PLACES, rounding=ROUND_HALF_UP)
    LOG.debug("[METERING-OPENAI] _quantize: %s -> %s", value, result)
    return result


def _safe_int(value: Any, default: int = 0) -> int:
    """Safely convert to int."""
    if value is None:
        LOG.debug("[METERING-OPENAI] _safe_int: None -> default=%d", default)
        return default
    try:
        result = int(value)
        LOG.debug("[METERING-OPENAI] _safe_int: %s -> %d", value, result)
        return result
    except (TypeError, ValueError) as e:
        LOG.debug("[METERING-OPENAI] _safe_int: %s failed (%s) -> default=%d", value, e, default)
        return default


class OpenAIMeteringExtractor:
    """
    Extracts metering data from OpenAI API responses.
    
    Supports:
    - Responses API (`usage.input_tokens`, `usage.output_tokens`)
    - Chat Completions API (`usage.prompt_tokens`, `usage.completion_tokens`)
    - Web search tool (`web_search_call` items)
    
    Usage:
        extractor = OpenAIMeteringExtractor(response_json)
        metering = extractor.extract()
    """
    
    def __init__(self, response: Dict[str, Any], model: str = "unknown"):
        _log_entry("OpenAIMeteringExtractor.__init__", model=model, response_keys=list((response or {}).keys()))
        
        self.response = response or {}
        self.model = model
        self._usage = response.get("usage") or {}
        self._output = response.get("output") or []  # Responses API
        self._choices = response.get("choices") or []  # Chat Completions
        
        LOG.info("[METERING-OPENAI] Initialized extractor for model=%s, has_usage=%s, output_items=%d, choices=%d",
                 model, bool(self._usage), len(self._output), len(self._choices))
        _log_step("__init__", "usage_keys", list(self._usage.keys()))
        _log_step("__init__", "output_types", [item.get("type") for item in self._output[:5]] if self._output else [])
    
    def extract_tokens(self) -> Dict[str, Any]:
        """
        Extract all token counts from response.
        
        Handles both Responses API and Chat Completions API formats.
        
        Returns dict with:
        - input_tokens
        - output_tokens
        - total_tokens
        - provider_specific:
            - reasoning_tokens (o1/o3 models)
            - cached_tokens
        """
        _log_entry("extract_tokens", usage=self._usage)
        
        u = self._usage
        
        # Responses API format
        input_tokens = _safe_int(u.get("input_tokens"))
        output_tokens = _safe_int(u.get("output_tokens"))
        total_tokens = _safe_int(u.get("total_tokens"))
        
        _log_step("extract_tokens", "responses_api_format", 
                  {"input": input_tokens, "output": output_tokens, "total": total_tokens})
        
        # Fall back to Chat Completions format
        if input_tokens == 0:
            input_tokens = _safe_int(u.get("prompt_tokens"))
            _log_step("extract_tokens", "fallback_prompt_tokens", input_tokens)
        if output_tokens == 0:
            output_tokens = _safe_int(u.get("completion_tokens"))
            _log_step("extract_tokens", "fallback_completion_tokens", output_tokens)
        
        # Calculate total if not provided
        if total_tokens == 0 and (input_tokens > 0 or output_tokens > 0):
            total_tokens = input_tokens + output_tokens
            _log_step("extract_tokens", "calculated_total", total_tokens)
        
        # Provider-specific fields. OpenAI Responses API uses input/output
        # details, while Chat Completions uses prompt/completion details.
        completion_details = u.get("completion_tokens_details") or {}
        output_details = u.get("output_tokens_details") or {}
        prompt_details = u.get("prompt_tokens_details") or {}
        input_details = u.get("input_tokens_details") or {}
        
        reasoning_tokens = max(
            _safe_int(completion_details.get("reasoning_tokens")),
            _safe_int(output_details.get("reasoning_tokens")),
            _safe_int(u.get("reasoning_tokens")),
        )
        cached_tokens = max(
            _safe_int(prompt_details.get("cached_tokens")),
            _safe_int(input_details.get("cached_tokens")),
            _safe_int(u.get("cached_tokens")),
        )
        audio_tokens = _safe_int(u.get("audio_tokens"))
        
        LOG.info("[METERING-OPENAI] Token counts: input=%d, output=%d, total=%d, reasoning=%d, cached=%d, audio=%d",
                 input_tokens, output_tokens, total_tokens, reasoning_tokens, cached_tokens, audio_tokens)
        
        result = {
            "input": input_tokens,
            "output": output_tokens,
            "total": total_tokens,
            "provider_specific": {
                "reasoning_tokens": reasoning_tokens,
                "cached_tokens": cached_tokens,
                # Audio tokens if present
                "audio_tokens": audio_tokens,
            }
        }
        
        _log_exit("extract_tokens", result)
        return result
    
    def extract_web_search(self) -> Dict[str, Any]:
        """
        Extract web search tool usage from Responses API output.
        
        Looks for `web_search_call` items in the output and counts actions:
        - search: web search query
        - open_page: opened a URL
        - find_in_page: searched within a page
        
        Returns dict with:
        - used: whether web search was invoked
        - provider_tool: "bing_web_search"
        - query_count: number of search actions
        - open_page_count: number of open_page actions
        - find_in_page_count: number of find_in_page actions
        - tool_calls: list of tool call dicts (for audit)
        """
        _log_entry("extract_web_search", output_count=len(self._output))
        
        search_calls = []
        search_count = 0
        open_page_count = 0
        find_in_page_count = 0
        
        # Process Responses API output items
        for idx, item in enumerate(self._output):
            item_type = item.get("type")
            
            if item_type == "web_search_call":
                search_calls.append(item)
                _log_step("extract_web_search", f"found_web_search_call[{idx}]", item.get("action", {}).get("type"))
                
                # Count actions
                action = item.get("action") or {}
                action_type = action.get("type")
                
                if action_type == "search":
                    # Count queries in the search action
                    queries = action.get("queries") or []
                    query_inc = len(queries) if queries else 1
                    search_count += query_inc
                    LOG.debug("[METERING-OPENAI] Web search action: queries=%s (count=%d)", queries, query_inc)
                elif action_type == "open_page":
                    open_page_count += 1
                    LOG.debug("[METERING-OPENAI] Web open_page action: url=%s", action.get("url"))
                elif action_type == "find_in_page":
                    find_in_page_count += 1
                    LOG.debug("[METERING-OPENAI] Web find_in_page action")
        
        used = len(search_calls) > 0
        
        LOG.info("[METERING-OPENAI] Web search: used=%s, tool_calls=%d, search_count=%d, open_page=%d, find_in_page=%d",
                 used, len(search_calls), search_count, open_page_count, find_in_page_count)
        
        result = {
            "used": used,
            "provider_tool": "bing_web_search",
            "billable_unit": "per_1k_calls_plus_tokens",
            "query_count": search_count,
            "open_page_count": open_page_count,
            "find_in_page_count": find_in_page_count,
            "tool_call_count": len(search_calls),
            "tool_calls": search_calls,  # Kept for audit
        }
        
        _log_exit("extract_web_search", {"used": used, "tool_call_count": len(search_calls)})
        return result
    
    def calculate_web_search_cost(
        self,
        web_search_data: Dict[str, Any],
        per_1k_calls_price: Optional[Decimal] = None,
    ) -> Decimal:
        """
        Calculate web search tool cost.
        
        OpenAI charges:
        1. Per 1k tool calls (prorated)
        2. Search content tokens at model rates (handled in token cost)
        
        Args:
            web_search_data: Output from extract_web_search()
            per_1k_calls_price: Price per 1000 tool calls
            
        Returns:
            Decimal cost with 6 decimal places (tool call portion only)
        """
        _log_entry("calculate_web_search_cost", 
                   web_search_used=web_search_data.get("used"),
                   tool_call_count=web_search_data.get("tool_call_count"),
                   per_1k_calls_price=per_1k_calls_price)
        
        if not web_search_data.get("used"):
            result = _quantize(0.0)
            LOG.debug("[METERING-OPENAI] Web search not used, cost=0")
            _log_exit("calculate_web_search_cost", result)
            return result
        
        if not per_1k_calls_price:
            LOG.warning("[METERING-OPENAI] No per_1k_calls_price provided for OpenAI web search")
            result = _quantize(0.0)
            _log_exit("calculate_web_search_cost", result)
            return result
        
        tool_call_count = web_search_data.get("tool_call_count", 0)
        
        # Price is per 1000 calls, prorate
        cost = (float(per_1k_calls_price) / 1000.0) * tool_call_count
        result = _quantize(cost)
        
        LOG.info("[METERING-OPENAI] Web search cost: %d tool_calls * ($%s/1000) = $%s",
                 tool_call_count, per_1k_calls_price, result)
        
        _log_exit("calculate_web_search_cost", result)
        return result
    
    def extract_raw_usage(self) -> Dict[str, Any]:
        """
        Return raw usage data for audit purposes.
        """
        _log_entry("extract_raw_usage", model=self.model)
        
        result = {
            "provider": "openai",
            "usage": self._usage,
            "model": self.response.get("model"),
            "id": self.response.get("id"),
        }
        
        LOG.debug("[METERING-OPENAI] Raw usage captured: usage_keys=%s, model=%s, id=%s",
                  list(self._usage.keys()),
                  self.response.get("model"),
                  self.response.get("id"))
        
        _log_exit("extract_raw_usage", {"keys": list(result.keys())})
        return result
    
    def extract(self) -> Dict[str, Any]:
        """
        Extract complete metering data.
        
        Returns a dict ready to be converted to MeteringEvent.
        """
        _log_entry("extract", model=self.model)
        
        LOG.info("[METERING-OPENAI] ========== Starting full extraction for model=%s ==========", self.model)
        
        tokens = self.extract_tokens()
        web_search = self.extract_web_search()
        raw_usage = self.extract_raw_usage()
        
        result = {
            "provider": "openai",
            "model": self.model,
            "tokens": tokens,
            "tools": {
                "web_search": web_search,
            },
            "raw_usage": raw_usage,
        }
        
        LOG.info("[METERING-OPENAI] ========== Extraction complete: input=%d, output=%d, web_search_used=%s ==========",
                 tokens.get("input", 0), tokens.get("output", 0), web_search.get("used", False))
        
        _log_exit("extract", {"provider": "openai", "model": self.model, "total_tokens": tokens.get("total", 0)})
        return result


def extract_openai_metering(
    response: Dict[str, Any],
    model: str = "unknown",
) -> Dict[str, Any]:
    """
    Convenience function to extract OpenAI metering.
    
    Args:
        response: Raw OpenAI API response JSON
        model: Model name (e.g., "gpt-5-mini")
        
    Returns:
        Dict with tokens, tools, raw_usage ready for MeteringEvent
    """
    LOG.info("[METERING-OPENAI] >>>>>>> extract_openai_metering called: model=%s, response_size=%d bytes",
             model, len(json.dumps(response or {})))
    
    try:
        extractor = OpenAIMeteringExtractor(response, model)
        result = extractor.extract()
        LOG.info("[METERING-OPENAI] <<<<<<< extract_openai_metering returning: total_tokens=%d, web_search_used=%s",
                 result.get("tokens", {}).get("total", 0),
                 result.get("tools", {}).get("web_search", {}).get("used", False))
        return result
    except Exception as e:
        LOG.error("[METERING-OPENAI] !!!!!!! extract_openai_metering FAILED: %s\n%s", e, traceback.format_exc())
        # Return minimal data so metering doesn't break execution
        return {
            "provider": "openai",
            "model": model,
            "tokens": {"input": 0, "output": 0, "total": 0},
            "tools": {},
            "raw_usage": {"provider": "openai", "error": str(e)},
        }


# Export
__all__ = [
    "OpenAIMeteringExtractor",
    "extract_openai_metering",
]
