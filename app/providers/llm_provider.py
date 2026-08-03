"""Answer-generation provider port."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence


class LLMProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Stable provider name safe to include in logs."""

    @abstractmethod
    def generate_answer(self, question: str, context_blocks: Sequence[str]) -> str:
        """Generate an answer using only the supplied evidence blocks."""
