from collections.abc import Sequence

from app.providers.embedding_provider import EmbeddingProvider
from evaluation.providers import CachingEmbeddingProvider


class _RecordingProvider(EmbeddingProvider):
    def __init__(self) -> None:
        self.document_calls: list[list[str]] = []
        self.query_calls: list[str] = []
        self.closed = False

    @property
    def name(self) -> str:
        return "recording"

    @property
    def model(self) -> str:
        return "recording-model"

    @property
    def dimensions(self) -> int:
        return 2

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        requested = list(texts)
        self.document_calls.append(requested)
        return [[float(len(text)), 0.0] for text in requested]

    def embed_query(self, text: str) -> list[float]:
        self.query_calls.append(text)
        return [float(len(text)), 0.0]

    def close(self) -> None:
        self.closed = True


def test_cache_deduplicates_documents_and_reuses_query_vectors() -> None:
    wrapped = _RecordingProvider()
    provider = CachingEmbeddingProvider(wrapped)

    vectors = provider.embed_documents(["alpha", "beta", "alpha"])
    query_vector = provider.embed_query("alpha")

    assert vectors == [[5.0, 0.0], [4.0, 0.0], [5.0, 0.0]]
    assert query_vector == [5.0, 0.0]
    assert wrapped.document_calls == [["alpha", "beta"]]
    assert wrapped.query_calls == []
    assert provider.name == "recording"
    assert provider.model == "recording-model"
    assert provider.dimensions == 2


def test_cache_closes_wrapped_provider() -> None:
    wrapped = _RecordingProvider()
    provider = CachingEmbeddingProvider(wrapped)

    provider.close()

    assert wrapped.closed
