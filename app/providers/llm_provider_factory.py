"""Create the configured generation provider without coupling business services."""

from app.core.config import Settings
from app.providers.deepseek_llm_provider import DeepSeekLLMProvider
from app.providers.llm_provider import LLMProvider
from app.providers.openai_llm_provider import OpenAILLMProvider


def create_llm_provider(settings: Settings) -> LLMProvider | None:
    """Return the selected provider, or None when its credential is absent."""
    common = {
        "model": settings.llm_model,
        "reasoning_effort": settings.llm_reasoning_effort,
        "verbosity": settings.llm_verbosity,
        "max_output_tokens": settings.llm_max_output_tokens,
        "timeout_seconds": settings.llm_timeout_seconds,
    }
    if settings.llm_provider == "openai":
        if settings.openai_api_key is None:
            return None
        return OpenAILLMProvider(api_key=settings.openai_api_key, **common)
    if settings.deepseek_api_key is None:
        return None
    return DeepSeekLLMProvider(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        **common,
    )
