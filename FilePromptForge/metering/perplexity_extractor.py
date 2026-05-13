"""
Metering extraction for native Perplexity Sonar responses.
"""
from __future__ import annotations

import logging
import traceback
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict

LOG = logging.getLogger(__name__)

DECIMAL_PLACES = Decimal("0.000001")


def _quantize(value: float) -> Decimal:
    return Decimal(str(value)).quantize(DECIMAL_PLACES, rounding=ROUND_HALF_UP)


def _safe_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class PerplexityMeteringExtractor:
    def __init__(self, response: Dict[str, Any], model: str = "unknown"):
        self.response = response or {}
        self.model = model
        self._usage = self.response.get("usage") or {}

    def extract_tokens(self) -> Dict[str, Any]:
        input_tokens = _safe_int(self._usage.get("prompt_tokens"))
        output_tokens = _safe_int(self._usage.get("completion_tokens"))
        total_tokens = _safe_int(self._usage.get("total_tokens")) or (input_tokens + output_tokens)
        reasoning_tokens = _safe_int(self._usage.get("reasoning_tokens"))
        citation_tokens = _safe_int(self._usage.get("citation_tokens"))

        return {
            "input": input_tokens,
            "output": output_tokens,
            "total": total_tokens,
            "provider_specific": {
                "reasoning_tokens": reasoning_tokens,
                "citation_tokens": citation_tokens,
            },
        }

    def extract_web_search(self) -> Dict[str, Any]:
        query_count = _safe_int(self._usage.get("num_search_queries"))
        return {
            "used": query_count > 0,
            "provider_tool": "perplexity_search",
            "billable_unit": "included_in_authoritative_cost",
            "query_count": query_count,
            "tool_call_count": query_count,
            "open_page_count": 0,
            "find_in_page_count": 0,
        }

    def extract_authoritative_cost(self) -> Dict[str, Any]:
        cost = self._usage.get("cost") or {}
        if not isinstance(cost, dict):
            return {"available": False}

        total_cost = cost.get("total_cost")
        if not isinstance(total_cost, (int, float)):
            return {"available": False}

        def _component(name: str):
            value = cost.get(name)
            if isinstance(value, (int, float)):
                return _quantize(float(value))
            return None

        return {
            "available": True,
            "total_cost_usd": _quantize(float(total_cost)),
            "input_cost_usd": _component("input_tokens_cost"),
            "output_cost_usd": _component("output_tokens_cost"),
            "citation_cost_usd": _component("citation_tokens_cost"),
            "reasoning_cost_usd": _component("reasoning_tokens_cost"),
            "search_queries_cost_usd": _component("search_queries_cost"),
            "request_cost_usd": _component("request_cost"),
        }

    def extract_raw_usage(self) -> Dict[str, Any]:
        return self._usage

    def extract(self) -> Dict[str, Any]:
        tokens = self.extract_tokens()
        web_search = self.extract_web_search()
        authoritative_cost = self.extract_authoritative_cost()
        raw_usage = self.extract_raw_usage()
        return {
            "provider": "perplexity",
            "model": self.model,
            "tokens": tokens,
            "tools": {
                "web_search": web_search,
            },
            "authoritative_cost": authoritative_cost,
            "raw_usage": raw_usage,
        }


def extract_perplexity_metering(response: Dict[str, Any], model: str = "unknown") -> Dict[str, Any]:
    try:
        return PerplexityMeteringExtractor(response, model).extract()
    except Exception as exc:
        LOG.error("[METERING-PERPLEXITY] extract_perplexity_metering failed: %s\n%s", exc, traceback.format_exc())
        return {
            "provider": "perplexity",
            "model": model,
            "tokens": {"input": 0, "output": 0, "total": 0},
            "tools": {},
            "raw_usage": {"provider": "perplexity", "error": str(exc)},
        }
