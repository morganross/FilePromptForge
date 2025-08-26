"""
grounder.py

Provider-agnostic Grounder orchestrator for FilePromptForge (FPF).

Responsibilities:
- Read grounding configuration and decide whether to attempt provider-side grounding.
- Perform capability detection (basic whitelist + runtime hints).
- Dispatch provider-specific requests to adapters (openai, openrouter, google).
- Normalize provider responses into a canonical schema.

Canonical response schema returned by Grounder.run():
{
  "text": str,
  "sources": [ { "title": str, "url": str, "snippet": str } ],
  "provider": str,
  "model": str,
  "method": "provider-tool" | "external-search" | "none",
  "tool_details": dict
}
"""

import os
import logging

# Adapters (import locally to avoid heavy deps at module import)
try:
    from .adapters import openai_adapter, openrouter_adapter, google_adapter
except Exception:
    # When adapters aren't present yet, we'll handle at runtime.
    openai_adapter = None
    openrouter_adapter = None
    google_adapter = None


class Grounder:
    def __init__(self, config, logger=None):
        """
        config: the Config object from gpt_processor_main.Config
        logger: optional logger
        """
        self.config = config
        self.logger = logger or logging.getLogger('gpt_processor.grounder')

        # Basic seeded whitelist for provider-side grounding support.
        # This is intentionally conservative and can be extended.
        self.openai_whitelist = {
            "gpt-4.1", "gpt-4o", "gpt-4o-mini-search-preview", "gpt-4o-search-preview",
            "o3-deep-research", "o4-mini-deep-research", "gpt-4.1-mini"
        }
        self.google_whitelist = {
            "gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-live-2.5-flash-preview"
        }
        # OpenRouter is model-catalog dependent; treat :online suffix as supportive
        # or rely on explicit config.model that includes ':online'

    def _is_model_whitelisted(self, provider, model):
        if not model:
            return False
        ml = model.lower()
        if provider.lower() == "openai":
            return any(m in ml for m in [s.lower() for s in self.openai_whitelist])
        if provider.lower() == "google":
            return any(m in ml for m in [s.lower() for s in self.google_whitelist])
        if provider.lower() == "openrouter":
            return ml.endswith(':online') or ':online' in ml
        return False

    def capability_check(self, provider, model):
        """
        Return True if provider-side grounding is likely supported for the given model.
        This is a fast, local check. Providers may still reject calls at runtime.
        """
        supported = self._is_model_whitelisted(provider, model)
        if self.logger:
            self.logger.debug(f"Capability check: provider={provider}, model={model}, supported={supported}")
        return supported

    def run(self, system_prompt, user_prompt, grounding_options=None):
        """
        Main entry point.
        grounding_options: dict that may include max_results, search_prompt, provider_override, allow_external_fallback (bool)
        Returns canonical response dict (see docstring).
        """
        provider = (grounding_options or {}).get('provider_override') or self.config.provider
        model = ''
        provider_conf = None

        if provider.lower() == 'openai':
            provider_conf = self.config.openai
            model = provider_conf.model
        elif provider.lower() == 'openrouter':
            provider_conf = self.config.openrouter
            model = provider_conf.model
        elif provider.lower() == 'google':
            # Config may not have google block; attempt to read from config dict if present
            provider_conf = getattr(self.config, 'google', None)
            model = provider_conf.model if provider_conf else ''
        else:
            # unknown provider; return no-op
            return {
                "text": "",
                "sources": [],
                "provider": provider,
                "model": model,
                "method": "none",
                "tool_details": {"error": f"Unknown provider {provider}"}
            }

        # If grounding not enabled in config, return none
        grounding_cfg = getattr(self.config, 'grounding', None)
        if not grounding_cfg or not getattr(grounding_cfg, 'enabled', False):
            if self.logger:
                self.logger.info("Grounding disabled in configuration; skipping provider-side grounding.")
            return {
                "text": "",
                "sources": [],
                "provider": provider,
                "model": model,
                "method": "none",
                "tool_details": {"note": "grounding disabled"}
            }

        # Capability check
        if not self.capability_check(provider, model):
            # If external fallback permitted, indicate unavailable; caller will decide.
            allow_fallback = (grounding_options or {}).get('allow_external_fallback', False) or getattr(grounding_cfg, 'allow_external_fallback', False)
            if self.logger:
                self.logger.warning(f"Provider-side grounding not available for provider={provider}, model={model}. allow_external_fallback={allow_fallback}")
            return {
                "text": "",
                "sources": [],
                "provider": provider,
                "model": model,
                "method": "none",
                "tool_details": {"error": "provider_grounding_unavailable", "allow_external_fallback": allow_fallback}
            }

        # Perform provider-specific grounding
        try:
            if provider.lower() == 'openai':
                if openai_adapter is None:
                    raise RuntimeError("openai_adapter not available")
                result = openai_adapter.perform_openai_grounding(provider_conf, system_prompt, user_prompt, grounding_options or {}, logger=self.logger)
            elif provider.lower() == 'openrouter':
                if openrouter_adapter is None:
                    raise RuntimeError("openrouter_adapter not available")
                result = openrouter_adapter.perform_openrouter_grounding(provider_conf, system_prompt, user_prompt, grounding_options or {}, logger=self.logger)
            elif provider.lower() == 'google':
                if google_adapter is None:
                    raise RuntimeError("google_adapter not available")
                result = google_adapter.perform_google_grounding(provider_conf, system_prompt, user_prompt, grounding_options or {}, logger=self.logger)
            else:
                result = {
                    "text": "",
                    "sources": [],
                    "provider": provider,
                    "model": model,
                    "method": "none",
                    "tool_details": {"error": "unsupported_provider"}
                }
        except Exception as e:
            if self.logger:
                self.logger.exception(f"Error running provider grounding: {e}")
            result = {
                "text": "",
                "sources": [],
                "provider": provider,
                "model": model,
                "method": "none",
                "tool_details": {"error": "exception", "exception": str(e)}
            }

        # Normalize result to canonical schema (perform limited validation)
        normalized = {
            "text": result.get("text", "") if isinstance(result, dict) else str(result),
            "sources": result.get("sources", []) if isinstance(result, dict) else [],
            "provider": provider,
            "model": model,
            "method": result.get("method", "provider-tool") if isinstance(result, dict) else "provider-tool",
            "tool_details": result.get("tool_details", {}) if isinstance(result, dict) else {}
        }
        return normalized
