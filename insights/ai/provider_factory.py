# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
AI Provider Factory
Returns the configured AI provider based on Insights Settings
"""

import frappe
from typing import Optional
from insights.ai.base_provider import BaseAIProvider


class AIProviderFactory:
    """Factory that returns the configured AI provider"""

    _providers = {}

    @classmethod
    def register(cls, name: str, provider_class):
        """Register a provider class"""
        cls._providers[name] = provider_class

    @classmethod
    def get_provider(cls, provider_name: Optional[str] = None) -> BaseAIProvider:
        """Get a specific provider by name"""
        if not provider_name:
            settings = frappe.get_single("Insights Settings")
            provider_name = getattr(settings, "ai_provider", None) or "openrouter"

        if provider_name not in cls._providers:
            # Lazy-load providers
            cls._ensure_providers_registered()

        provider_class = cls._providers.get(provider_name)
        if not provider_class:
            raise ValueError(f"Unknown AI provider: {provider_name}. Available: {list(cls._providers.keys())}")
        # Pass the requested name through: a client whose behaviour depends on
        # which provider was asked for (Ollama local vs cloud) must not fall back
        # to the *saved* ai_provider, or "test before saving" probes the wrong host.
        return provider_class(provider_name)

    @classmethod
    def get_client(cls) -> BaseAIProvider:
        """Get the currently configured provider. Drop-in replacement for OpenRouterClient()"""
        return cls.get_provider()

    @classmethod
    def _ensure_providers_registered(cls):
        """Lazy-register all known providers. Each provider key checked independently
        so partial registration (e.g. ollama but not ollama_cloud) self-heals."""
        if "openrouter" not in cls._providers:
            try:
                from insights.ai.openrouter_client import OpenRouterClient
                cls.register("openrouter", OpenRouterClient)
            except ImportError:
                pass
        if "ollama" not in cls._providers or "ollama_cloud" not in cls._providers:
            try:
                from insights.ai.ollama_client import OllamaClient
                if "ollama" not in cls._providers:
                    cls.register("ollama", OllamaClient)
                if "ollama_cloud" not in cls._providers:
                    cls.register("ollama_cloud", OllamaClient)
            except ImportError:
                pass
        if "moonshot" not in cls._providers:
            try:
                from insights.ai.moonshot_client import MoonshotClient
                cls.register("moonshot", MoonshotClient)
            except ImportError:
                pass
        if "openai" not in cls._providers:
            try:
                from insights.ai.openai_client import OpenAIClient
                cls.register("openai", OpenAIClient)
            except ImportError:
                pass
        if "nvidia" not in cls._providers:
            try:
                from insights.ai.nvidia_client import NvidiaClient
                cls.register("nvidia", NvidiaClient)
            except ImportError:
                pass

    @classmethod
    def get_available_providers(cls) -> dict:
        """Get list of available providers and their status"""
        cls._ensure_providers_registered()
        result = {}
        for name, provider_class in cls._providers.items():
            try:
                provider = provider_class()
                result[name] = {
                    "name": name,
                    "enabled": provider.is_enabled(),
                    "provider_name": provider.provider_name
                }
            except Exception:
                result[name] = {"name": name, "enabled": False, "provider_name": name}
        return result
