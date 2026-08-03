"""Answer-generation provider port."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Final

INSUFFICIENT_EVIDENCE_MARKER: Final = "INSUFFICIENT_EVIDENCE"


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
    def generate_answer(self, question: str, context_blocks: Sequence[str]) -> str:
        """Generate an answer using only the supplied evidence blocks."""

    @abstractmethod
    def close(self) -> None:
        """Release network resources owned by the provider."""
