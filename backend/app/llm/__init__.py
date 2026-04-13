"""LLM provider factory.

Usage:
    from app.llm import get_llm_provider
    provider = get_llm_provider()
    result = await provider.classify_role(...)
"""

from app.config import settings
from app.llm.provider import LLMProvider
from app.logging_config import get_logger

logger = get_logger(__name__)

_provider: LLMProvider | None = None


def get_llm_provider() -> LLMProvider:
    """Return the configured LLM provider (singleton)."""
    global _provider
    if _provider is not None:
        return _provider

    from app.llm.ollama import OllamaProvider

    _provider = OllamaProvider()
    logger.info(
        "llm.provider_selected",
        provider="ollama",
        model=settings.ollama_model,
    )

    return _provider
