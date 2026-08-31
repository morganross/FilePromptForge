"""
MeteringEvent builder for FPF.

Combines:
- Provider-specific extractors (Gemini, OpenAI)
- Pricing lookup
- Cost calculation
- Event formatting

Emits events to:
- FPF log file (existing behavior)
- ACM metering endpoint (new)

PRECISION: All costs use Decimal with 6 decimal places.
LOGGING: EXTREME verbose - logs every operation, all values, all decisions.
"""
from __future__ import annotations

import json
import logging
import os
import traceback
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4

try:
    from ..paths import default_pricing_index
except ImportError:
    from paths import default_pricing_index

LOG = logging.getLogger(__name__)

# ============================================================================
# Logging utilities
# ============================================================================

def _log_entry(func_name: str, **kwargs) -> None:
    """Log function entry with all parameters."""
    LOG.debug("[METERING-BUILDER] ENTER %s with: %s", func_name, kwargs)

def _log_exit(func_name: str, result: Any) -> None:
    """Log function exit with result."""
    LOG.debug("[METERING-BUILDER] EXIT %s returning: %s", func_name, result)

def _log_step(func_name: str, step: str, value: Any = None) -> None:
    """Log intermediate step within a function."""
    LOG.debug("[METERING-BUILDER] %s | %s: %s", func_name, step, value)

# Quantize to 6 decimal places
DECIMAL_PLACES = Decimal("0.000001")


def _quantize(value: float) -> Decimal:
    """Convert float to Decimal with exactly 6 decimal places."""
    result = Decimal(str(value)).quantize(DECIMAL_PLACES, rounding=ROUND_HALF_UP)
    LOG.debug("[METERING-BUILDER] _quantize: %s -> %s", value, result)
    return result


def _format_decimal(d) -> str:
    """Format Decimal to string with exactly 6 decimal places. None = unknown."""
    if d is None:
        return None
    result = f"{d:.6f}"
    LOG.debug("[METERING-BUILDER] _format_decimal: %s -> '%s'", d, result)
    return result


def _as_nonnegative_int(value: Any) -> int:
    if isinstance(value, bool) or value is None:
        return 0
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        try:
            return max(0, int(float(value)))
        except (TypeError, ValueError):
            return 0


def _as_nonnegative_decimal(value: Any) -> Optional[Decimal]:
    if isinstance(value, bool) or value is None:
        return None
    try:
        parsed = Decimal(str(value))
    except Exception:
        return None
    if parsed < 0:
        return None
    return parsed


class MeteringEventBuilder:
    """
    Builds MeteringEvents from provider responses.
    
    Usage:
        builder = MeteringEventBuilder(
            provider="google",
            model="gemini-2.5-flash",
            run_id="abc123",
            phase="fpf.generate",
        )
        event = builder.build_event(response, latency_ms=1234)
        builder.emit(event)
    """
    
    def __init__(
        self,
        provider: str,
        model: str,
        run_id: str,
        phase: str = "fpf.generate",
        user_uuid: Optional[str] = None,
        logical_task_id: Optional[str] = None,
        document_id: Optional[str] = None,
        iteration: int = 1,
        pricing_path: Optional[str] = None,
    ):
        _log_entry("MeteringEventBuilder.__init__", 
                   provider=provider, model=model, run_id=run_id, phase=phase,
                   user_uuid=user_uuid, logical_task_id=logical_task_id,
                   document_id=document_id, iteration=iteration)
        
        self.provider = provider.lower()
        self.model = model
        self.run_id = run_id
        self.phase = phase
        self.user_uuid = user_uuid
        self.logical_task_id = logical_task_id or str(uuid4())
        self.document_id = document_id
        self.iteration = iteration
        
        # Pricing
        self._pricing_path = pricing_path
        self._pricing_data: Optional[Dict] = None
        self._pricing_record: Optional[Dict] = None
        self._ws_pricing: Optional[Dict] = None  # Web search supplemental pricing
        
        # Retry tracking
        self._attempt_count = 0
        self._parent_attempt_id: Optional[str] = None
        
        LOG.info("[METERING-BUILDER] Initialized: provider=%s model=%s run_id=%s phase=%s user=%s",
                 self.provider, self.model, self.run_id, self.phase, self.user_uuid)
    
    def _load_pricing(self) -> None:
        """Load pricing data if not already loaded."""
        _log_entry("_load_pricing", pricing_path=self._pricing_path)
        
        if self._pricing_data is not None:
            LOG.debug("[METERING-BUILDER] Pricing already loaded, skipping")
            return
        
        if not self._pricing_path:
            # Default path
            self._pricing_path = str(default_pricing_index())
            LOG.debug("[METERING-BUILDER] Using default pricing path: %s", self._pricing_path)
        
        try:
            with open(self._pricing_path, "r") as f:
                self._pricing_data = json.load(f)
            LOG.info("[METERING-BUILDER] Loaded pricing data: %d records from %s", 
                     len(self._pricing_data or []), self._pricing_path)
        except Exception as e:
            LOG.warning("[METERING-BUILDER] Failed to load pricing from %s: %s", self._pricing_path, e)
            self._pricing_data = []
        
        # Load supplemental web search pricing
        self._load_ws_pricing()
    
    def _load_ws_pricing(self) -> None:
        """Load supplemental web search pricing from web_search_pricing.json."""
        if self._ws_pricing is not None:
            return
        
        base_dir = Path(__file__).parent.parent
        ws_path = base_dir / "pricing" / "web_search_pricing.json"
        
        try:
            with open(ws_path, "r") as f:
                self._ws_pricing = json.load(f)
            LOG.info("[METERING-BUILDER] Loaded web search pricing from %s", ws_path)
        except Exception as e:
            LOG.warning("[METERING-BUILDER] Failed to load web search pricing from %s: %s", ws_path, e)
            self._ws_pricing = {}
    
    def _get_ws_price_google(self, billing_unit: str) -> Optional[float]:
        """Get Google grounding price from web_search_pricing.json."""
        if not self._ws_pricing:
            return None
        
        google = self._ws_pricing.get("google", {})
        
        if billing_unit == "per_grounded_prompt":
            rec = google.get("per_grounded_prompt", {})
            price = rec.get("price_per_unit_usd")
            if price is not None:
                LOG.debug("[METERING-BUILDER] Google grounding per_grounded_prompt price: $%s", price)
                return float(price)
        elif billing_unit == "per_query":
            rec = google.get("per_query", {})
            price = rec.get("price_per_unit_usd")
            if price is not None:
                LOG.debug("[METERING-BUILDER] Google grounding per_query price: $%s", price)
                return float(price)
        
        LOG.warning("[METERING-BUILDER] No Google grounding price for billing_unit=%s", billing_unit)
        return None
    
    def _get_ws_price_openai(self, model: str) -> Optional[float]:
        """Get OpenAI per-call web search price from web_search_pricing.json."""
        if not self._ws_pricing:
            return None
        
        openai_cfg = self._ws_pricing.get("openai", {})
        model_lower = model.lower()
        
        # Check if it's a search-preview model (non-reasoning, higher per-call rate)
        preview_cfg = openai_cfg.get("web_search_preview_non_reasoning", {})
        preview_models = [m.lower() for m in preview_cfg.get("applies_to", [])]
        if any(p in model_lower for p in preview_models):
            price = preview_cfg.get("per_call_usd")
            if price is not None:
                LOG.debug("[METERING-BUILDER] OpenAI web search preview price: $%s/call", price)
                return float(price)
        
        # Standard web_search pricing
        ws_cfg = openai_cfg.get("web_search", {})
        price = ws_cfg.get("per_call_usd")
        if price is not None:
            LOG.debug("[METERING-BUILDER] OpenAI web search standard price: $%s/call", price)
            return float(price)
        
        LOG.warning("[METERING-BUILDER] No OpenAI web search price for model=%s", model)
        return None
    
    def _get_ws_price_anthropic(self) -> Optional[float]:
        """Get Anthropic per-search web search price from web_search_pricing.json."""
        if not self._ws_pricing:
            return None
        
        anthropic_cfg = self._ws_pricing.get("anthropic", {})
        ws_cfg = anthropic_cfg.get("web_search", {})
        price = ws_cfg.get("per_search_usd")
        if price is not None:
            LOG.debug("[METERING-BUILDER] Anthropic web search price: $%s/search", price)
            return float(price)
        
        LOG.warning("[METERING-BUILDER] No Anthropic web search price in web_search_pricing.json")
        return None
    
    def _find_pricing_record(self) -> Optional[Dict]:
        """Find pricing record for current model."""
        _log_entry("_find_pricing_record", provider=self.provider, model=self.model)
        
        if self._pricing_record is not None:
            LOG.debug("[METERING-BUILDER] Using cached pricing record for %s/%s", self.provider, self.model)
            return self._pricing_record
        
        self._load_pricing()
        
        # Build model slug
        if self.provider in ("openaidp",):
            canonical_provider = "openai"
        elif self.provider in ("googledp",):
            canonical_provider = "google"
        else:
            canonical_provider = self.provider
        model_slug = f"{canonical_provider}/{self.model}"
        
        LOG.debug("[METERING-BUILDER] Looking for pricing record: model_slug=%s", model_slug)
        
        for rec in (self._pricing_data or []):
            if rec.get("model") == model_slug:
                self._pricing_record = rec
                LOG.info("[METERING-BUILDER] Found pricing record for %s: input=$%s/M, output=$%s/M",
                         model_slug, 
                         rec.get("input_price_per_million_usd"),
                         rec.get("output_price_per_million_usd"))
                _log_exit("_find_pricing_record", {"model": model_slug, "found": True})
                return rec
        
        LOG.warning("[METERING-BUILDER] No pricing record found for %s", model_slug)
        _log_exit("_find_pricing_record", None)
        return None

    def _calculate_billable_token_buckets(self, tokens: Dict[str, Any]) -> Dict[str, Any]:
        """
        Map provider-specific token names into ACM's two stored price buckets.
        Raw subtype counts stay in provider_specific for audit.
        """
        provider_specific = tokens.get("provider_specific") or {}
        if not isinstance(provider_specific, dict):
            provider_specific = {}

        raw_input_tokens = _as_nonnegative_int(tokens.get("input"))
        raw_output_tokens = _as_nonnegative_int(tokens.get("output"))
        input_components: Dict[str, int] = {"input_tokens": raw_input_tokens}
        output_components: Dict[str, int] = {"output_tokens": raw_output_tokens}
        notes = ["two_bucket_input_output_pricing"]
        provider = str(self.provider or "").lower()

        def add_input(name: str, value: Any) -> None:
            count = _as_nonnegative_int(value)
            if count > 0:
                input_components[name] = count

        def add_output(name: str, value: Any) -> None:
            count = _as_nonnegative_int(value)
            if count > 0:
                output_components[name] = count

        if provider in {"google", "googledp"}:
            add_input("tool_use_prompt_tokens", provider_specific.get("tool_use_prompt_tokens"))
            add_input("cached_tokens", provider_specific.get("cached_tokens"))
            add_output("thoughts_tokens", provider_specific.get("thoughts_tokens"))
            notes.append("google_thoughts_output_tool_cache_input")
        elif provider == "anthropic":
            add_input("cached_tokens", provider_specific.get("cached_tokens"))
            add_input("cache_creation_tokens", provider_specific.get("cache_creation_tokens"))
            notes.append("anthropic_cache_tokens_input_priced")
            if _as_nonnegative_int(provider_specific.get("reasoning_tokens")) > 0:
                notes.append("anthropic_reasoning_count_audit_only_output_tokens_used")
        elif provider in {"openai", "openaidp", "openrouter", "perplexity", "codexexecapi"}:
            notes.append(f"{provider}_top_level_input_output_used")
            if _as_nonnegative_int(provider_specific.get("reasoning_tokens")) > 0:
                notes.append("reasoning_tokens_audit_only_output_tokens_used")
            if _as_nonnegative_int(provider_specific.get("cached_tokens")) > 0:
                notes.append("cached_tokens_audit_only_input_tokens_used")
        else:
            if raw_input_tokens <= 0:
                add_input("cached_tokens", provider_specific.get("cached_tokens"))
                add_input("cache_creation_tokens", provider_specific.get("cache_creation_tokens"))
                add_input("tool_use_prompt_tokens", provider_specific.get("tool_use_prompt_tokens"))
            if raw_output_tokens <= 0:
                add_output("reasoning_tokens", provider_specific.get("reasoning_tokens"))
                add_output("thoughts_tokens", provider_specific.get("thoughts_tokens"))
            notes.append("unknown_provider_top_level_tokens_preferred")

        result = {
            "billable_input_tokens": sum(input_components.values()),
            "billable_output_tokens": sum(output_components.values()),
            "input_priced_components": input_components,
            "output_priced_components": output_components,
            "notes": notes,
        }
        LOG.info(
            "[METERING-BUILDER] Billable token buckets: provider=%s model=%s input=%d output=%d components_in=%s components_out=%s",
            self.provider,
            self.model,
            result["billable_input_tokens"],
            result["billable_output_tokens"],
            input_components,
            output_components,
        )
        return result
    
    def _calculate_token_cost(
        self,
        input_tokens: int,
        output_tokens: int,
    ) -> tuple[Decimal, Decimal, Decimal]:
        """
        Calculate token costs.
        
        Returns:
            (input_cost, output_cost, total_token_cost) - all 6 decimal places
        """
        _log_entry("_calculate_token_cost", input_tokens=input_tokens, output_tokens=output_tokens)
        
        rec = self._find_pricing_record()
        
        if not rec:
            LOG.warning("[METERING-BUILDER] No pricing record — costs recorded as unknown")
            result = (None, None, None)
            _log_exit("_calculate_token_cost", result)
            return result
        
        input_price = rec.get("input_price_per_million_usd")
        output_price = rec.get("output_price_per_million_usd")
        input_price_decimal = _as_nonnegative_decimal(input_price)
        output_price_decimal = _as_nonnegative_decimal(output_price)
        
        LOG.debug("[METERING-BUILDER] Prices: input=$%s/M, output=$%s/M", input_price, output_price)
        
        input_cost = None
        output_cost = None
        
        if input_price_decimal is not None:
            input_cost = _quantize((input_tokens / 1_000_000.0) * float(input_price_decimal))
            _log_step("_calculate_token_cost", "input_cost", 
                     f"{input_tokens} tokens * ${input_price}/M = ${input_cost}")
        else:
            LOG.warning("[METERING-BUILDER] Input price unknown for %s/%s", self.provider, self.model)
        
        if output_price_decimal is not None:
            output_cost = _quantize((output_tokens / 1_000_000.0) * float(output_price_decimal))
            _log_step("_calculate_token_cost", "output_cost",
                     f"{output_tokens} tokens * ${output_price}/M = ${output_cost}")
        else:
            LOG.warning("[METERING-BUILDER] Output price unknown for %s/%s", self.provider, self.model)
        
        # Total is None if any component is unknown
        if input_cost is not None and output_cost is not None:
            total = input_cost + output_cost
        elif input_cost is not None:
            total = input_cost
        elif output_cost is not None:
            total = output_cost
        else:
            total = None
        
        LOG.info("[METERING-BUILDER] Token costs: input=%s, output=%s, total=%s", 
                 input_cost, output_cost, total)
        
        _log_exit("_calculate_token_cost", (input_cost, output_cost, total))
        return input_cost, output_cost, total
    
    def _extract_metering(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract metering data using provider-specific extractor.
        """
        _log_entry("_extract_metering", provider=self.provider, response_keys=list((response or {}).keys()))
        
        LOG.info("[METERING-BUILDER] Extracting metering for provider=%s model=%s", self.provider, self.model)
        
        try:
            if self.provider == "google":
                from metering import extract_gemini_metering
                result = extract_gemini_metering(response, self.model)
                LOG.debug("[METERING-BUILDER] Gemini extraction complete: tokens=%s", 
                         result.get("tokens", {}).get("total", 0))
                _log_exit("_extract_metering", {"provider": "google", "total_tokens": result.get("tokens", {}).get("total", 0)})
                return result
            elif self.provider == "googledp":
                from metering.googledp_extractor import extract_googledp_metering
                result = extract_googledp_metering(response, self.model)
                LOG.debug("[METERING-BUILDER] GoogleDP extraction complete: tokens=%s",
                         result.get("tokens", {}).get("total", 0))
                _log_exit("_extract_metering", {"provider": "googledp", "total_tokens": result.get("tokens", {}).get("total", 0)})
                return result
            elif self.provider in ("openai", "openaidp", "codexexecapi"):
                from metering.openai_extractor import extract_openai_metering
                result = extract_openai_metering(response, self.model)
                LOG.debug("[METERING-BUILDER] OpenAI extraction complete: tokens=%s",
                         result.get("tokens", {}).get("total", 0))
                _log_exit("_extract_metering", {"provider": "openai", "total_tokens": result.get("tokens", {}).get("total", 0)})
                return result
            elif self.provider == "anthropic":
                from metering.anthropic_extractor import extract_anthropic_metering
                result = extract_anthropic_metering(response, self.model)
                LOG.debug("[METERING-BUILDER] Anthropic extraction complete: tokens=%s",
                         result.get("tokens", {}).get("total", 0))
                _log_exit("_extract_metering", {"provider": "anthropic", "total_tokens": result.get("tokens", {}).get("total", 0)})
                return result
            elif self.provider == "openrouter":
                from metering.openrouter_extractor import extract_openrouter_metering
                result = extract_openrouter_metering(response, self.model)
                LOG.debug("[METERING-BUILDER] OpenRouter extraction complete: tokens=%s, authoritative_cost=%s",
                         result.get("tokens", {}).get("total", 0),
                         result.get("authoritative_cost", {}).get("total_cost_usd"))
                _log_exit("_extract_metering", {"provider": "openrouter", "total_tokens": result.get("tokens", {}).get("total", 0)})
                return result
            elif self.provider == "perplexity":
                from metering.perplexity_extractor import extract_perplexity_metering
                result = extract_perplexity_metering(response, self.model)
                LOG.debug("[METERING-BUILDER] Perplexity extraction complete: tokens=%s, authoritative_cost=%s",
                         result.get("tokens", {}).get("total", 0),
                         result.get("authoritative_cost", {}).get("total_cost_usd"))
                _log_exit("_extract_metering", {"provider": "perplexity", "total_tokens": result.get("tokens", {}).get("total", 0)})
                return result
            else:
                LOG.warning("[METERING-BUILDER] Unknown provider %s, using minimal extraction", self.provider)
                result = {
                    "provider": self.provider,
                    "model": self.model,
                    "tokens": {"input": 0, "output": 0, "total": 0},
                    "tools": {},
                    "raw_usage": {"provider": self.provider},
                }
                _log_exit("_extract_metering", result)
                return result
        except Exception as e:
            LOG.error("[METERING-BUILDER] Extraction failed for %s: %s\n%s", self.provider, e, traceback.format_exc())
            return {
                "provider": self.provider,
                "model": self.model,
                "tokens": {"input": 0, "output": 0, "total": 0},
                "tools": {},
                "raw_usage": {"provider": self.provider, "extraction_error": str(e)},
            }
    
    def _generate_idempotency_key(self, attempt_id: str) -> str:
        """
        Generate idempotency key.
        
        Format: sha256(run_id:doc_id:model:iteration:attempt_id)[:32]
        """
        import hashlib
        parts = f"{self.run_id}:{self.document_id or 'none'}:{self.model}:{self.iteration}:{attempt_id}"
        result = hashlib.sha256(parts.encode()).hexdigest()[:32]
        LOG.debug("[METERING-BUILDER] Generated idempotency_key: %s from parts: %s", result, parts)
        return result
    
    def build_event(
        self,
        response: Dict[str, Any],
        latency_ms: int,
        status: str = "success",
        error: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Build a complete MeteringEvent dict.
        
        Args:
            response: Raw provider response JSON
            latency_ms: Request latency in milliseconds
            status: "success", "error", or "cancelled"
            error: Error message if status is error
            request_id: Provider's request ID if available
            
        Returns:
            Dict matching MeteringEvent schema
        """
        _log_entry("build_event", 
                   latency_ms=latency_ms, status=status, error=error, 
                   request_id=request_id, response_size=len(json.dumps(response or {})))
        
        LOG.info("[METERING-BUILDER] ========== Building metering event: provider=%s model=%s status=%s ==========",
                 self.provider, self.model, status)
        
        # Generate attempt ID
        attempt_id = str(uuid4())
        self._attempt_count += 1
        
        # Track retry parent
        retry_sequence = self._attempt_count - 1
        retry_parent = self._parent_attempt_id if retry_sequence > 0 else None
        
        # Update parent for next attempt
        self._parent_attempt_id = attempt_id
        
        LOG.debug("[METERING-BUILDER] Attempt tracking: attempt_id=%s, retry_sequence=%d, parent=%s",
                  attempt_id, retry_sequence, retry_parent)
        
        # Extract metering data
        metering = self._extract_metering(response)
        tokens = metering.get("tokens", {})
        tools = metering.get("tools", {})
        raw_usage = metering.get("raw_usage", {})
        
        # Calculate costs from exactly two ACM price buckets: input and output.
        input_tokens = _as_nonnegative_int(tokens.get("input", 0))
        output_tokens = _as_nonnegative_int(tokens.get("output", 0))
        provider_specific = tokens.get("provider_specific") or {}
        if not isinstance(provider_specific, dict):
            provider_specific = {}
        billing_buckets = self._calculate_billable_token_buckets(tokens)
        billable_input_tokens = billing_buckets["billable_input_tokens"]
        billable_output_tokens = billing_buckets["billable_output_tokens"]
        input_cost, output_cost, token_cost = self._calculate_token_cost(
            billable_input_tokens,
            billable_output_tokens,
        )
        reasoning_tokens = (
            _as_nonnegative_int(provider_specific.get("reasoning_tokens"))
            + _as_nonnegative_int(provider_specific.get("thoughts_tokens"))
        )
        cached_tokens = (
            _as_nonnegative_int(provider_specific.get("cached_tokens"))
            + _as_nonnegative_int(provider_specific.get("cache_creation_tokens"))
        )
        reasoning_cost = _quantize(0)
        cached_cost = _quantize(0)
        
        # Tool cost
        tool_cost = None
        web_search = tools.get("web_search", {})
        if web_search.get("used"):
            LOG.debug("[METERING-BUILDER] Web search tool was used, loading pricing from web_search_pricing.json")
            
            if self.provider in ("google", "googledp"):
                billing_unit = web_search.get("billable_unit", "per_grounded_prompt")
                ws_price = self._get_ws_price_google(billing_unit)
                
                if ws_price is not None:
                    if billing_unit == "per_grounded_prompt":
                        # Flat fee per grounded prompt
                        tool_cost = _quantize(ws_price)
                        LOG.info("[METERING-BUILDER] Gemini grounding (per_grounded_prompt): flat $%s", tool_cost)
                    elif billing_unit == "per_query":
                        # Per individual search query
                        query_count = web_search.get("query_count", 0)
                        tool_cost = _quantize(ws_price * query_count)
                        LOG.info("[METERING-BUILDER] Gemini grounding (per_query): %d * $%s = $%s",
                                 query_count, ws_price, tool_cost)
                else:
                    LOG.warning("[METERING-BUILDER] Grounding used but no price in web_search_pricing.json — recorded as unknown")
            
            elif self.provider in ("openai", "openaidp"):
                # OpenAI: per tool call (each web_search_call item = 1 billable call)
                per_call_price = self._get_ws_price_openai(self.model)
                
                if per_call_price is not None:
                    # tool_call_count is the billable unit, NOT query_count
                    tool_call_count = web_search.get("tool_call_count", web_search.get("query_count", 0))
                    tool_cost = _quantize(per_call_price * tool_call_count)
                    LOG.info("[METERING-BUILDER] OpenAI web search: %d tool_calls * $%s/call = $%s",
                             tool_call_count, per_call_price, tool_cost)
                else:
                    LOG.warning("[METERING-BUILDER] OpenAI web search used but no price in web_search_pricing.json — recorded as unknown")
            
            elif self.provider == "anthropic":
                # Anthropic: $10 / 1,000 searches = $0.01 per search
                search_count = web_search.get("query_count", web_search.get("tool_call_count", 0))
                per_search_price = self._get_ws_price_anthropic()
                if per_search_price is not None:
                    tool_cost = _quantize(per_search_price * search_count)
                    LOG.info("[METERING-BUILDER] Anthropic web search: %d searches * $%s/search = $%s",
                             search_count, per_search_price, tool_cost)
                else:
                    # Hardcode known price as fallback: $0.01/search
                    tool_cost = _quantize(0.01 * search_count)
                    LOG.info("[METERING-BUILDER] Anthropic web search (hardcoded): %d searches * $0.01 = $%s",
                             search_count, tool_cost)
            
            elif self.provider == "openrouter":
                # OpenRouter: web search cost is already included in the authoritative usage.cost field
                # Record $0 for tool_cost to avoid double-counting
                tool_cost = _quantize(0)
                LOG.info("[METERING-BUILDER] OpenRouter web search: cost included in authoritative usage.cost, tool_cost=$0")
            
            elif self.provider == "perplexity":
                # Native Perplexity search/citation charges come from usage.cost; avoid double-counting here.
                tool_cost = _quantize(0)
                LOG.info("[METERING-BUILDER] Perplexity search costs are included in authoritative usage.cost, tool_cost=$0 until override")
            
            elif self.provider == "codexexecapi":
                # CodexExecAPI uses ChatGPT/Codex quota, not ACM API-credit pricing.
                # Keep usage exact, but leave dollar cost unknown until an explicit pricing policy exists.
                LOG.info("[METERING-BUILDER] CodexExecAPI web search uses Codex quota; tool cost recorded as unknown")
            
            else:
                LOG.warning("[METERING-BUILDER] Web search used by unknown provider %s — recorded as unknown", self.provider)
        else:
            tool_cost = _quantize(0)  # Web search not used = $0 (not unknown)
        
        # OpenRouter authoritative cost override — use usage.cost when available
        authoritative_cost = metering.get("authoritative_cost", {})
        authoritative_total_override = None
        if self.provider in ("openrouter", "perplexity") and authoritative_cost.get("available"):
            authoritative_total_override = authoritative_cost["total_cost_usd"]
            LOG.info(
                "[METERING-BUILDER] %s authoritative cost available: $%s (overrides token-based calc)",
                self.provider,
                authoritative_total_override,
            )

            if authoritative_cost.get("input_cost_usd") is not None:
                input_cost = authoritative_cost["input_cost_usd"]
            if authoritative_cost.get("output_cost_usd") is not None:
                output_cost = authoritative_cost["output_cost_usd"]

            if input_cost is not None and output_cost is not None:
                token_cost = input_cost + output_cost
            elif input_cost is not None:
                token_cost = input_cost
            elif output_cost is not None:
                token_cost = output_cost

            if self.provider == "perplexity":
                citation_cost = authoritative_cost.get("citation_cost_usd") or _quantize(0)
                search_queries_cost = authoritative_cost.get("search_queries_cost_usd") or _quantize(0)
                request_cost = authoritative_cost.get("request_cost_usd") or _quantize(0)
                tool_cost = citation_cost + search_queries_cost + request_cost
                LOG.info(
                    "[METERING-BUILDER] Perplexity authoritative tool cost override: citation=%s search=%s request=%s total_tools=%s",
                    citation_cost,
                    search_queries_cost,
                    request_cost,
                    tool_cost,
                )
        
        # Total cost — None if any component is unknown
        known_parts = [p for p in [token_cost, tool_cost] if p is not None]
        total_cost = _quantize(sum(known_parts)) if known_parts else None
        has_unknown = token_cost is None or tool_cost is None
        
        # If OpenRouter provides authoritative cost, use it as the total
        if authoritative_total_override is not None:
            total_cost = authoritative_total_override
            has_unknown = False
            LOG.info(
                "[METERING-BUILDER] Using %s authoritative cost as total: $%s (token-based was $%s)",
                self.provider,
                authoritative_total_override,
                _quantize(sum(known_parts)) if known_parts else None,
            )
        
        LOG.info(
            "[METERING-BUILDER] Cost summary: billable_input=%d billable_output=%d tokens=%s + tools=%s = total=%s%s",
            billable_input_tokens,
            billable_output_tokens,
            token_cost,
            tool_cost,
            total_cost,
            " (PARTIAL - some unknown)" if has_unknown else "",
        )
        
        # Get pricing info
        rec = self._find_pricing_record()
        pricing_source = None
        if rec:
            pricing_source = {
                "name": rec.get("source", "manual_index"),
                "source_url": rec.get("source_url"),
                "last_updated": rec.get("last_updated"),
            }
            LOG.debug("[METERING-BUILDER] Pricing source: %s", pricing_source.get("name"))
        
        # Build event
        event = {
            "event_type": f"llm_call.{status}" if status != "success" else "llm_call.completed",
            "idempotency_key": self._generate_idempotency_key(attempt_id),
            "attempt_id": attempt_id,
            "logical_task_id": self.logical_task_id,
            "retry_parent_attempt_id": retry_parent,
            "retry_sequence": retry_sequence,
            "ts": datetime.utcnow().isoformat() + "Z",
            "user_uuid": self.user_uuid,
            "run_id": self.run_id,
            "phase": self.phase,
            "provider": self.provider,
            "model": self.model,
            "request_id": request_id,
            "tokens": {
                "input": input_tokens,
                "output": output_tokens,
                "total": tokens.get("total", input_tokens + output_tokens),
                "provider_specific": {
                    **(tokens.get("provider_specific") or {}),
                    "billable_input_tokens": billable_input_tokens,
                    "billable_output_tokens": billable_output_tokens,
                    "billing_rule": "two_bucket_input_output_only",
                    "input_priced_components": billing_buckets["input_priced_components"],
                    "output_priced_components": billing_buckets["output_priced_components"],
                    "billing_notes": billing_buckets["notes"],
                    "document_id": self.document_id or "",
                    "source_doc_id": (tokens.get("provider_specific") or {}).get("source_doc_id") or self.document_id or "",
                },
            },
            "tools": {
                "web_search": {
                    "used": web_search.get("used", False),
                    "provider_tool": web_search.get("provider_tool"),
                    "billable_unit": web_search.get("billable_unit"),
                    "query_count": web_search.get("query_count", 0),
                    "tool_call_count": web_search.get("tool_call_count", 0),
                    "open_page_count": web_search.get("open_page_count", 0),
                    "find_in_page_count": web_search.get("find_in_page_count", 0),
                } if web_search else None,
            },
            "cost": {
                "currency": "USD",
                "model_tokens": _format_decimal(token_cost),
                "input_tokens_cost": _format_decimal(input_cost),
                "output_tokens_cost": _format_decimal(output_cost),
                "cached_input_cost": _format_decimal(cached_cost),
                "reasoning_cost": _format_decimal(reasoning_cost),
                "tools": _format_decimal(tool_cost),
                "total": _format_decimal(total_cost),
                "pricing_source": pricing_source,
                "confidence": "exact" if ((rec and not has_unknown) or authoritative_total_override is not None) else "unknown",
                "notes": [] if authoritative_total_override is not None else [n for n in ["token_cost_unknown" if token_cost is None else None, "tool_cost_unknown" if tool_cost is None else None, f"reasoning_tokens_priced_as_output:{reasoning_tokens}" if reasoning_tokens > 0 else None, f"cached_tokens_priced_as_input:{cached_tokens}" if cached_tokens > 0 else None, *billing_buckets["notes"]] if n],
            },
            "latency_ms": latency_ms,
            "status": status,
            "error": error,
            "raw_usage": raw_usage,
        }
        
        LOG.info("[METERING-BUILDER] ========== Event built: attempt=%s input=%d output=%d total_cost=$%s ==========",
                 attempt_id[:8], input_tokens, output_tokens, total_cost)
        if total_cost is None and (
            input_tokens > 0
            or output_tokens > 0
            or bool(web_search and web_search.get("used"))
        ):
            LOG.warning(
                "[METERING-BUILDER] COST UNKNOWN WITH USAGE: run=%s attempt=%s provider=%s model=%s phase=%s input=%d output=%d web_search=%s document_id=%s",
                self.run_id,
                attempt_id,
                self.provider,
                self.model,
                self.phase,
                input_tokens,
                output_tokens,
                bool(web_search and web_search.get("used")),
                self.document_id,
            )
        
        _log_exit("build_event", {"attempt_id": attempt_id[:8], "total_cost": str(total_cost)})
        return event
    
    def emit_to_log(self, event: Dict[str, Any], log_dir: Optional[str] = None) -> Optional[str]:
        """
        Write event to a JSON log file.
        
        By default writes to $FPF_LOG_DIR/metering/ if FPF_LOG_DIR is set,
        otherwise falls back to FilePromptForge/logs/metering/.
        
        Returns:
            Path to log file, or None if failed
        """
        _log_entry("emit_to_log", log_dir=log_dir, attempt_id=event.get("attempt_id", "")[:8])
        
        if not log_dir:
            # Use FPF_LOG_DIR if set (ACM passes this to FPF subprocess)
            fpf_log_dir = os.environ.get("FPF_LOG_DIR")
            if fpf_log_dir:
                log_dir = str(Path(fpf_log_dir) / "metering")
                LOG.debug("[METERING-BUILDER] Using FPF_LOG_DIR: %s", log_dir)
            else:
                base_dir = Path(__file__).parent.parent
                log_dir = str(base_dir / "logs" / "metering")
                LOG.debug("[METERING-BUILDER] Using default log dir: %s", log_dir)
        
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)
        
        try:
            filename = f"{datetime.now().strftime('%Y%m%dT%H%M%S')}-{event['attempt_id'][:8]}-metering.json"
            filepath = log_path / filename
            
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(event, f, indent=2, ensure_ascii=False)
            
            LOG.info("[METERING-BUILDER] +++++ Wrote metering log: %s (cost=$%s)", filepath, event.get("cost", {}).get("total", "?"))
            _log_exit("emit_to_log", str(filepath))
            return str(filepath)
        except Exception as e:
            LOG.error("[METERING-BUILDER] !!!!! Failed to write metering log: %s\n%s", e, traceback.format_exc())
            _log_exit("emit_to_log", None)
            return None
    
    def emit_to_acm(self, event: Dict[str, Any], acm_url: Optional[str] = None) -> bool:
        """
        POST event to ACM metering endpoint.
        
        Env Vars:
            ACM_METERING_URL: Full URL to metering endpoint (e.g., https://localhost/api/metering/events)
            ACM_AUTH_TOKEN: Bearer token for authentication
        
        Returns:
            True if successful, False otherwise
        """
        _log_entry("emit_to_acm", acm_url=acm_url, attempt_id=event.get("attempt_id", "")[:8])
        
        if not acm_url:
            acm_url = os.environ.get("ACM_METERING_URL")
        
        if not acm_url:
            LOG.debug("[METERING-BUILDER] ACM_METERING_URL not set, skipping ACM emit")
            _log_exit("emit_to_acm", False)
            return False
        
        auth_token = os.environ.get("ACM_AUTH_TOKEN")
        LOG.debug("[METERING-BUILDER] ACM emission: url=%s, has_auth=%s", acm_url, bool(auth_token))
        
        try:
            import urllib.request
            import ssl
            
            data = json.dumps(event).encode("utf-8")
            
            headers = {"Content-Type": "application/json"}
            if auth_token:
                headers["Authorization"] = f"Bearer {auth_token}"
            
            req = urllib.request.Request(
                acm_url,
                data=data,
                headers=headers,
                method="POST",
            )
            
            # Allow self-signed certs for local ACM
            ctx = ssl.create_default_context()
            if os.environ.get("ACM_ALLOW_SELF_SIGNED", "").lower() in ("1", "true", "yes"):
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                LOG.debug("[METERING-BUILDER] SSL: allowing self-signed certs")
            
            LOG.debug("[METERING-BUILDER] POSTing %d bytes to ACM...", len(data))
            
            with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
                if resp.status in (200, 201):
                    LOG.info("[METERING-BUILDER] +++++ Emitted to ACM: attempt=%s cost=$%s status=%d", 
                             event.get("attempt_id", "")[:8], 
                             event.get("cost", {}).get("total", "?"),
                             resp.status)
                    _log_exit("emit_to_acm", True)
                    return True
                else:
                    LOG.warning("[METERING-BUILDER] ACM returned non-success status %d", resp.status)
                    _log_exit("emit_to_acm", False)
                    return False
        except Exception as e:
            LOG.warning("[METERING-BUILDER] !!!!! Failed to emit to ACM: %s", e)
            LOG.debug("[METERING-BUILDER] ACM emit traceback: %s", traceback.format_exc())
            _log_exit("emit_to_acm", False)
            return False
    
    def emit(self, event: Dict[str, Any]) -> None:
        """
        Emit event to all destinations (log + ACM).
        """
        _log_entry("emit", attempt_id=event.get("attempt_id", "")[:8], total_cost=event.get("cost", {}).get("total", "?"))
        
        LOG.info("[METERING-BUILDER] >>>>> Emitting metering event: run=%s model=%s cost=$%s",
                 event.get("run_id", "?")[:8], event.get("model", "?"), event.get("cost", {}).get("total", "?"))
        
        log_result = self.emit_to_log(event)
        acm_result = self.emit_to_acm(event)
        
        LOG.info("[METERING-BUILDER] <<<<< Emission complete: log=%s, acm=%s",
                 "OK" if log_result else "SKIPPED", "OK" if acm_result else "SKIPPED")
        
        _log_exit("emit", {"log": bool(log_result), "acm": acm_result})


def build_metering_event(
    provider: str,
    model: str,
    response: Dict[str, Any],
    run_id: str,
    latency_ms: int,
    phase: str = "fpf.generate",
    user_uuid: Optional[str] = None,
    logical_task_id: Optional[str] = None,
    document_id: Optional[str] = None,
    iteration: int = 1,
    status: str = "success",
    error: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Convenience function to build a metering event.
    """
    LOG.info("[METERING-BUILDER] >>>>>>> build_metering_event called: provider=%s model=%s run=%s",
             provider, model, run_id[:8] if run_id else "?")
    
    try:
        builder = MeteringEventBuilder(
            provider=provider,
            model=model,
            run_id=run_id,
            phase=phase,
            user_uuid=user_uuid,
            logical_task_id=logical_task_id,
            document_id=document_id,
            iteration=iteration,
            pricing_path=os.environ.get("FPF_PRICING_PATH"),
        )
        result = builder.build_event(response, latency_ms, status, error)
        LOG.info("[METERING-BUILDER] <<<<<<< build_metering_event returning: attempt=%s cost=$%s",
                 result.get("attempt_id", "")[:8], result.get("cost", {}).get("total", "?"))
        return result
    except Exception as e:
        LOG.error("[METERING-BUILDER] !!!!!!! build_metering_event FAILED: %s\n%s", e, traceback.format_exc())
        # Return a minimal event so we don't break the caller
        return {
            "event_type": "llm_call.error",
            "attempt_id": str(uuid4()),
            "run_id": run_id,
            "provider": provider,
            "model": model,
            "tokens": {"input": 0, "output": 0, "total": 0},
            "cost": {"currency": "USD", "model_tokens": "0.000000", "input_tokens_cost": "0.000000", "output_tokens_cost": "0.000000", "reasoning_cost": "0.000000", "tools": "0.000000", "total": "0.000000"},
            "status": "error",
            "error": f"metering_build_failed: {str(e)}",
        }


# Export
__all__ = [
    "MeteringEventBuilder",
    "build_metering_event",
]
