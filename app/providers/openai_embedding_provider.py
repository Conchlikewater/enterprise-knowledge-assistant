"""OpenAI embedding adapter with batching and privacy-safe errors."""

from __future__ import annotations

from collections.abc import Sequence
from math import isfinite
from typing import Any

from openai import OpenAI

from app.core.exceptions import EmbeddingProviderError
from app.providers.embedding_provider import EmbeddingProvider


class OpenAIEmbeddingProvider(EmbeddingProvider):
    def __init__(
        self,
        api_key: str,
        model: str = "text-embedding-3-small",
        dimensions: int = 1536,
        batch_size: int = 64,
        timeout_seconds: float = 30.0,
        client: Any | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("api_key must not be empty")
        if not model.strip():
            raise ValueError("model must not be empty")
        if dimensions <= 0:
            raise ValueError("dimensions must be positive")
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

        self._model = model
        self._dimensions = dimensions
        self._batch_size = batch_size
        self._owns_client = client is None
        self._client = client or OpenAI(
            api_key=api_key,
            timeout=timeout_seconds,
            max_retries=2,
        )

    @property
    def name(self) -> str:
        return "openai"

    @property
    def model(self) -> str:
        return self._model

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        normalized_texts = self._validate_texts(texts)
        if not normalized_texts:
            return []

        embeddings: list[list[float]] = []
        for start in range(0, len(normalized_texts), self._batch_size):
            batch = normalized_texts[start : start + self._batch_size]
            embeddings.extend(self._embed_batch(batch))
        return embeddings

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        try:
            response = self._client.embeddings.create(
                input=texts,
                model=self._model,
                dimensions=self._dimensions,
                encoding_format="float",
            )
            ordered_items = sorted(response.data, key=lambda item: item.index)
            if [item.index for item in ordered_items] != list(range(len(texts))):
                raise EmbeddingProviderError()
            return [self._validate_embedding(item.embedding) for item in ordered_items]
        except EmbeddingProviderError:
            raise
        except Exception as exc:
            raise EmbeddingProviderError() from exc

    def _validate_embedding(self, embedding: Sequence[float]) -> list[float]:
        if len(embedding) != self._dimensions:
            raise EmbeddingProviderError()
        vector = [float(value) for value in embedding]
        if not all(isfinite(value) for value in vector):
            raise EmbeddingProviderError()
        return vector

    @staticmethod
    def _validate_texts(texts: Sequence[str]) -> list[str]:
        normalized = list(texts)
        if any(not isinstance(text, str) or not text.strip() for text in normalized):
            raise ValueError("embedding inputs must be non-empty strings")
        return normalized
