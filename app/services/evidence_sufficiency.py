"""Pure evidence sufficiency rule for the bounded R6 retry decision."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import isfinite

from app.domain.models import RetrievalResult


@dataclass(frozen=True, slots=True)
class EvidenceAssessment:
    required_result_count: int
    relevant_result_count: int

    @property
    def should_retry(self) -> bool:
        return self.relevant_result_count < self.required_result_count


class EvidenceSufficiencyPolicy:
    def assess(
        self,
        results: Sequence[RetrievalResult],
        *,
        top_k: int,
        score_threshold: float | None,
    ) -> EvidenceAssessment:
        if top_k < 1:
            raise ValueError("top_k must be positive")
        if score_threshold is not None and (
            not isfinite(score_threshold) or not -1.0 <= score_threshold <= 1.0
        ):
            raise ValueError("score_threshold must be between -1 and 1")

        required_count = min(2, top_k)
        relevant_count = sum(
            score_threshold is None or result.score >= score_threshold
            for result in results
        )
        return EvidenceAssessment(
            required_result_count=required_count,
            relevant_result_count=relevant_count,
        )
