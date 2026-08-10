"""Deterministic, dependency-light providers for offline quality checks."""

from __future__ import annotations

import re
from collections.abc import Sequence
from hashlib import sha256
from itertools import pairwise
from math import sqrt

from app.providers.embedding_provider import EmbeddingProvider
from app.providers.llm_provider import LLMProvider

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
_STOP_WORDS = frozenset(
    {
        "a",
        "after",
        "all",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "before",
        "by",
        "do",
        "does",
        "each",
        "for",
        "from",
        "how",
        "in",
        "is",
        "it",
        "must",
        "of",
        "on",
        "or",
        "the",
        "their",
        "to",
        "what",
        "when",
        "which",
        "with",
        "within",
    }
)


class HashingEmbeddingProvider(EmbeddingProvider):
    """Map exact lexical features into normalized deterministic vectors."""

    def __init__(self, dimensions: int = 1024) -> None:
        if dimensions <= 0:
            raise ValueError("dimensions must be positive")
        self._dimensions = dimensions

    @property
    def name(self) -> str:
        return "offline-hashing"

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)

    def close(self) -> None:
        pass

    def _embed(self, text: str) -> list[float]:
        tokens = [
            _normalize_token(token)
            for token in _TOKEN_PATTERN.findall(text.lower())
            if token not in _STOP_WORDS
        ]
        if not tokens:
            raise ValueError("evaluation text must contain lexical features")
        features = [*tokens, *(f"{a}_{b}" for a, b in pairwise(tokens))]
        vector = [0.0] * self._dimensions
        for feature in features:
            digest = sha256(feature.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self._dimensions
            vector[index] += 1.0
        magnitude = sqrt(sum(value * value for value in vector))
        return [value / magnitude for value in vector]


class CachingEmbeddingProvider(EmbeddingProvider):
    """Cache exact inputs so evaluation does not pay for duplicate embeddings."""

    def __init__(self, wrapped: EmbeddingProvider) -> None:
        self._wrapped = wrapped
        self._cache: dict[str, tuple[float, ...]] = {}

    @property
    def name(self) -> str:
        return self._wrapped.name

    @property
    def model(self) -> str | None:
        model = getattr(self._wrapped, "model", None)
        return model if isinstance(model, str) else None

    @property
    def dimensions(self) -> int:
        return self._wrapped.dimensions

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        requested = list(texts)
        missing = list(
            dict.fromkeys(text for text in requested if text not in self._cache)
        )
        if missing:
            embedded = self._wrapped.embed_documents(missing)
            if len(embedded) != len(missing):
                raise ValueError(
                    "wrapped provider returned an unexpected embedding count"
                )
            self._cache.update(
                (text, tuple(vector))
                for text, vector in zip(missing, embedded, strict=True)
            )
        return [list(self._cache[text]) for text in requested]

    def embed_query(self, text: str) -> list[float]:
        cached = self._cache.get(text)
        if cached is None:
            cached = tuple(self._wrapped.embed_query(text))
            self._cache[text] = cached
        return list(cached)

    def close(self) -> None:
        self._wrapped.close()


def _normalize_token(token: str) -> str:
    if len(token) > 4 and token.endswith("ies"):
        return f"{token[:-3]}y"
    if len(token) > 4 and token.endswith("s") and not token.endswith(("ss", "us")):
        return token[:-1]
    return token


class EvaluationLLMProvider(LLMProvider):
    """Return a stable answer so citation construction can be evaluated offline."""

    @property
    def name(self) -> str:
        return "offline-evaluation"

    @property
    def model(self) -> str:
        return "deterministic-grounded-answer"

    def generate_answer(
        self,
        question: str,
        context_blocks: Sequence[str],
    ) -> str:
        if not question.strip() or not context_blocks:
            raise ValueError("evaluation answer requires a question and evidence")
        return "Evaluation answer grounded in the retrieved evidence [1]."

    def close(self) -> None:
        pass
