"""DeepSeek V4 adapter using its OpenAI-compatible Responses API."""

from __future__ import annotations

from typing import Any, Final

from app.providers.openai_llm_provider import OpenAILLMProvider

DEFAULT_DEEPSEEK_BASE_URL: Final = "https://api.deepseek.com"
DEFAULT_DEEPSEEK_MODEL: Final = "deepseek-v4-flash"
_RESPONSES_API_MODELS: Final = frozenset({DEFAULT_DEEPSEEK_MODEL})


class DeepSeekLLMProvider(OpenAILLMProvider):
    """Generate grounded answers through DeepSeek's Responses API."""

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_DEEPSEEK_MODEL,
        reasoning_effort: str = "none",
        verbosity: str = "low",
        max_output_tokens: int = 800,
        timeout_seconds: float = 60.0,
        base_url: str = DEFAULT_DEEPSEEK_BASE_URL,
        client: Any | None = None,
    ) -> None:
        if model not in _RESPONSES_API_MODELS:
            raise ValueError(
                "DeepSeek Responses API currently supports deepseek-v4-flash only"
            )
        super().__init__(
            api_key=api_key,
            model=model,
            reasoning_effort=reasoning_effort,
            verbosity=verbosity,
            max_output_tokens=max_output_tokens,
            timeout_seconds=timeout_seconds,
            base_url=base_url,
            client=client,
        )

    @property
    def name(self) -> str:
        return "deepseek"
