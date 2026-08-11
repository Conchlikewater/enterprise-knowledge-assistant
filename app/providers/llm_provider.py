"""Answer-generation provider port."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

INSUFFICIENT_EVIDENCE_MARKER: Final = "INSUFFICIENT_EVIDENCE"


@dataclass(frozen=True, slots=True)
class LLMTokenUsage:
    """Provider-neutral token counts returned by one generation request."""

    input_tokens: int
    output_tokens: int
    cached_input_tokens: int = 0
    reasoning_tokens: int = 0

    def __post_init__(self) -> None:
        counts = (
            self.input_tokens,
            self.output_tokens,
            self.cached_input_tokens,
            self.reasoning_tokens,
        )
        if any(count < 0 for count in counts):
            raise ValueError("token counts must be non-negative")
        if self.cached_input_tokens > self.input_tokens:
            raise ValueError("cached_input_tokens cannot exceed input_tokens")
        if self.reasoning_tokens > self.output_tokens:
            raise ValueError("reasoning_tokens cannot exceed output_tokens")

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True, slots=True)
class LLMGenerationResult:
    """Text plus optional accounting metadata from an LLM provider."""

    text: str
    usage: LLMTokenUsage | None = None

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("generated text must not be empty")


class LLMProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Stable provider name safe to include in logs."""

    @property
    @abstractmethod
    def model(self) -> str:
        """Configured model identifier safe to include in diagnostics."""

    @abstractmethod
    def generate_answer(
        self,
        question: str,
        context_blocks: Sequence[str],
    ) -> LLMGenerationResult:
        """Generate an answer and optional usage using only supplied evidence."""

    @abstractmethod
    def close(self) -> None:
        """Release network resources owned by the provider."""
