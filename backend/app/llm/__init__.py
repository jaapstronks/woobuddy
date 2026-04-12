"""LLM provider factory.

Usage:
    from app.llm import get_llm_provider
    provider = get_llm_provider()
    result = await provider.classify_role(...)
"""

import logging

from app.config import settings
from app.llm.provider import LLMProvider

logger = logging.getLogger(__name__)

_provider: LLMProvider | None = None


def get_llm_provider() -> LLMProvider:
    """Return the configured LLM provider (singleton)."""
    global _provider
    if _provider is not None:
        return _provider

    if settings.llm_provider == "anthropic":
        from app.llm.anthropic import AnthropicProvider

        _provider = AnthropicProvider()
        logger.info("Using Anthropic LLM provider (model: %s)", settings.anthropic_model)
    else:
        from app.llm.ollama import OllamaProvider

        _provider = OllamaProvider()
        logger.info("Using Ollama LLM provider (model: %s)", settings.ollama_model)

    return _provider
