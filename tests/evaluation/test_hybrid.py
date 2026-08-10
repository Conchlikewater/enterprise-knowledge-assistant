from hashlib import sha256
from uuid import UUID

import pytest

from app.domain.models import Chunk, RetrievalResult
from app.storage.vector_store import VectorStore
from evaluation.hybrid import (
    BM25Retriever,
    HybridRetrievalService,
    RecordingVectorStore,
    reciprocal_rank_fusion,
)

FIRST_DOCUMENT_ID = UUID("00000000-0000-0000-0000-000000000001")
SECOND_DOCUMENT_ID = UUID("00000000-0000-0000-0000-000000000002")


class _FakeVectorStore(VectorStore):
    def __init__(self) -> None:
        self.initialized = False
        self.closed = False
        self.upserted: list[Chunk] = []
        self.deleted: list[UUID] = []

    @property
    def dimensions(self) -> int:
        return 3

    def initialize(self) -> None:
        self.initialized = True

    def health(self) -> bool:
        return self.initialized and not self.closed

    def upsert(self, chunks, vectors) -> None:
        assert len(chunks) == len(vectors)
        self.upserted.extend(chunks)

    def search(self, query_vector, document_ids, limit) -> list[RetrievalResult]:
        return []

    def delete_by_document(self, document_id: UUID) -> None:
        self.deleted.append(document_id)

    def close(self) -> None:
        self.closed = True


class _DenseStub:
    def __init__(self, results: list[RetrievalResult]) -> None:
        self.results = results
        self.calls: list[tuple[int, float | None]] = []

    def search(
        self,
        query: str,
        document_ids: list[UUID],
        top_k: int,
        score_threshold: float | None = None,
    ) -> list[RetrievalResult]:
        self.calls.append((top_k, score_threshold))
        return self.results[:top_k]


def _chunk(
    chunk_number: int,
    text: str,
    *,
    document_id: UUID = FIRST_DOCUMENT_ID,
) -> Chunk:
    return Chunk(
        chunk_id=UUID(f"00000000-0000-0000-0000-{chunk_number:012d}"),
        document_id=document_id,
        chunk_index=chunk_number,
        text=text,
        filename=f"{document_id}.txt",
        content_hash=sha256(text.encode()).hexdigest(),
    )


def _result(chunk: Chunk, score: float) -> RetrievalResult:
    return RetrievalResult(
        chunk_id=chunk.chunk_id,
        document_id=chunk.document_id,
        filename=chunk.filename,
        text=chunk.text,
        score=score,
    )


def test_bm25_prioritizes_exact_identifier_and_respects_scope() -> None:
    exact = _chunk(1, "Incident procedure SEC-204 requires immediate escalation.")
    semantic_only = _chunk(2, "Security incidents must be reported quickly.")
    out_of_scope = _chunk(
        3,
        "SEC-204 appears in a different selected policy.",
        document_id=SECOND_DOCUMENT_ID,
    )
    retriever = BM25Retriever([semantic_only, out_of_scope, exact])

    results = retriever.search("What does SEC-204 require?", [FIRST_DOCUMENT_ID], 5)

    assert [result.chunk_id for result in results] == [exact.chunk_id]
    assert all(result.document_id == FIRST_DOCUMENT_ID for result in results)


def test_bm25_returns_no_result_without_lexical_overlap() -> None:
    retriever = BM25Retriever([_chunk(1, "annual leave approval workflow")])

    assert retriever.search("satellite routing", [FIRST_DOCUMENT_ID], 5) == []


def test_rrf_rewards_chunks_supported_by_both_rankings() -> None:
    shared = _chunk(1, "shared evidence")
    dense_only = _chunk(2, "semantic evidence")
    lexical_only = _chunk(3, "exact identifier evidence")
    dense_ranking = [_result(dense_only, 0.9), _result(shared, 0.8)]
    lexical_ranking = [_result(shared, 7.0), _result(lexical_only, 5.0)]

    fused = reciprocal_rank_fusion(
        [dense_ranking, lexical_ranking],
        limit=3,
        rank_constant=60,
    )

    assert fused[0].chunk_id == shared.chunk_id
    assert {result.chunk_id for result in fused[1:]} == {
        dense_only.chunk_id,
        lexical_only.chunk_id,
    }
    assert fused[0].score > fused[1].score


def test_rrf_rejects_conflicting_or_duplicate_chunks() -> None:
    chunk = _chunk(1, "original evidence")
    duplicate_ranking = [_result(chunk, 1.0), _result(chunk, 0.5)]
    conflicting = RetrievalResult(
        chunk_id=chunk.chunk_id,
        document_id=chunk.document_id,
        filename=chunk.filename,
        text="conflicting evidence",
        score=1.0,
    )

    with pytest.raises(ValueError, match="duplicate"):
        reciprocal_rank_fusion([duplicate_ranking], limit=2)
    with pytest.raises(ValueError, match="conflicting"):
        reciprocal_rank_fusion([[_result(chunk, 1.0)], [conflicting]], limit=2)


def test_recording_vector_store_keeps_exact_chunks_and_deletes_by_document() -> None:
    wrapped = _FakeVectorStore()
    store = RecordingVectorStore(wrapped)
    first = _chunk(1, "first")
    second = _chunk(2, "second", document_id=SECOND_DOCUMENT_ID)

    store.initialize()
    store.upsert([first, second], [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])

    assert store.health()
    assert store.dimensions == 3
    assert store.chunks == (first, second)
    assert wrapped.upserted == [first, second]

    store.delete_by_document(FIRST_DOCUMENT_ID)
    assert store.chunks == (second,)
    assert wrapped.deleted == [FIRST_DOCUMENT_ID]

    store.close()
    assert wrapped.closed


def test_hybrid_service_fuses_candidates_and_applies_normalized_threshold() -> None:
    shared = _chunk(1, "SEC-204 shared evidence")
    dense_only = _chunk(2, "semantic incident escalation")
    lexical_only = _chunk(3, "SEC-204 exact identifier")
    dense = _DenseStub([_result(dense_only, 0.9), _result(shared, 0.8)])
    lexical = BM25Retriever([shared, dense_only, lexical_only])
    service = HybridRetrievalService(dense, lexical)  # type: ignore[arg-type]

    results = service.search(
        "What does SEC-204 require?",
        [FIRST_DOCUMENT_ID],
        top_k=3,
        score_threshold=0.75,
    )

    assert [result.chunk_id for result in results] == [shared.chunk_id]
    assert results[0].score <= 1.0
    assert dense.calls == [(12, None)]


@pytest.mark.parametrize("threshold", [-0.1, 1.1, float("inf")])
def test_hybrid_service_rejects_invalid_threshold(threshold: float) -> None:
    service = HybridRetrievalService(  # type: ignore[arg-type]
        _DenseStub([]),
        BM25Retriever([]),
    )

    with pytest.raises(ValueError, match="score_threshold"):
        service.search("query", [FIRST_DOCUMENT_ID], 5, threshold)


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (lambda: BM25Retriever([], k1=0), "k1"),
        (lambda: BM25Retriever([], b=1.1), "b"),
        (
            lambda: BM25Retriever([_chunk(1, "first"), _chunk(1, "duplicate")]),
            "unique",
        ),
    ],
)
def test_bm25_rejects_invalid_configuration(factory, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        factory()
