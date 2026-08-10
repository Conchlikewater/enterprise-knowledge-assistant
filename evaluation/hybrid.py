"""Dependency-light BM25 retrieval and reciprocal-rank fusion experiments."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Sequence
from math import isfinite, log
from uuid import UUID

from app.domain.models import Chunk, RetrievalResult
from app.services.retrieval_service import RetrievalService
from app.storage.vector_store import VectorStore

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+(?:[-_.][a-z0-9]+)*")


class RecordingVectorStore(VectorStore):
    """Record the exact ingested chunks while delegating vector operations."""

    def __init__(self, wrapped: VectorStore) -> None:
        self._wrapped = wrapped
        self._chunks: dict[UUID, Chunk] = {}

    @property
    def dimensions(self) -> int:
        return self._wrapped.dimensions

    @property
    def chunks(self) -> tuple[Chunk, ...]:
        return tuple(
            sorted(
                self._chunks.values(),
                key=lambda chunk: (
                    str(chunk.document_id),
                    chunk.chunk_index,
                    str(chunk.chunk_id),
                ),
            )
        )

    def initialize(self) -> None:
        self._wrapped.initialize()

    def health(self) -> bool:
        return self._wrapped.health()

    def upsert(
        self,
        chunks: Sequence[Chunk],
        vectors: Sequence[Sequence[float]],
    ) -> None:
        for chunk in chunks:
            existing = self._chunks.get(chunk.chunk_id)
            if existing is not None and existing != chunk:
                raise ValueError("the same chunk ID has conflicting chunk data")
        self._wrapped.upsert(chunks, vectors)
        self._chunks.update((chunk.chunk_id, chunk) for chunk in chunks)

    def search(
        self,
        query_vector: Sequence[float],
        document_ids: Sequence[UUID],
        limit: int,
    ) -> list[RetrievalResult]:
        return self._wrapped.search(query_vector, document_ids, limit)

    def delete_by_document(self, document_id: UUID) -> None:
        self._wrapped.delete_by_document(document_id)
        self._chunks = {
            chunk_id: chunk
            for chunk_id, chunk in self._chunks.items()
            if chunk.document_id != document_id
        }

    def close(self) -> None:
        self._wrapped.close()


class BM25Retriever:
    """Small in-memory BM25 index for the tracked evaluation corpus."""

    def __init__(
        self,
        chunks: Sequence[Chunk],
        *,
        k1: float = 1.5,
        b: float = 0.75,
    ) -> None:
        if k1 <= 0:
            raise ValueError("k1 must be positive")
        if not 0.0 <= b <= 1.0:
            raise ValueError("b must be between 0 and 1")
        if len({chunk.chunk_id for chunk in chunks}) != len(chunks):
            raise ValueError("chunk IDs must be unique")

        self._chunks = tuple(chunks)
        self._k1 = k1
        self._b = b
        self._tokens = tuple(_tokenize(chunk.text) for chunk in self._chunks)
        self._term_frequencies = tuple(Counter(tokens) for tokens in self._tokens)
        self._document_frequencies = Counter(
            token for tokens in self._tokens for token in set(tokens)
        )
        self._average_length = (
            sum(len(tokens) for tokens in self._tokens) / len(self._tokens)
            if self._tokens
            else 0.0
        )

    def search(
        self,
        query: str,
        document_ids: Sequence[UUID],
        limit: int,
    ) -> list[RetrievalResult]:
        normalized_query = query.strip()
        if not normalized_query:
            raise ValueError("query must not be empty")
        if not document_ids:
            raise ValueError("document_ids must not be empty")
        if limit <= 0:
            raise ValueError("limit must be positive")

        query_terms = tuple(dict.fromkeys(_tokenize(normalized_query)))
        if not query_terms or not self._chunks:
            return []
        allowed_document_ids = set(document_ids)
        scored: list[RetrievalResult] = []
        for chunk, tokens, frequencies in zip(
            self._chunks,
            self._tokens,
            self._term_frequencies,
            strict=True,
        ):
            if chunk.document_id not in allowed_document_ids:
                continue
            score = sum(
                self._term_score(term, frequencies, len(tokens)) for term in query_terms
            )
            if score <= 0.0:
                continue
            scored.append(
                RetrievalResult(
                    chunk_id=chunk.chunk_id,
                    document_id=chunk.document_id,
                    filename=chunk.filename,
                    page_number=chunk.page_number,
                    text=chunk.text,
                    score=score,
                )
            )
        return sorted(
            scored,
            key=lambda result: (-result.score, *_stable_result_key(result)),
        )[:limit]

    def _term_score(
        self,
        term: str,
        frequencies: Counter[str],
        document_length: int,
    ) -> float:
        frequency = frequencies.get(term, 0)
        if frequency == 0:
            return 0.0
        document_count = len(self._chunks)
        document_frequency = self._document_frequencies[term]
        inverse_document_frequency = log(
            1.0
            + (document_count - document_frequency + 0.5) / (document_frequency + 0.5)
        )
        length_ratio = (
            document_length / self._average_length if self._average_length else 0.0
        )
        denominator = frequency + self._k1 * (1.0 - self._b + self._b * length_ratio)
        return inverse_document_frequency * frequency * (self._k1 + 1.0) / denominator


class HybridRetrievalService:
    """Fuse dense and BM25 rankings for evaluation without changing production."""

    def __init__(
        self,
        dense_retriever: RetrievalService,
        lexical_retriever: BM25Retriever,
        *,
        candidate_multiplier: int = 4,
        rank_constant: int = 60,
        max_top_k: int = 50,
    ) -> None:
        if candidate_multiplier < 1:
            raise ValueError("candidate_multiplier must be positive")
        if rank_constant < 1:
            raise ValueError("rank_constant must be positive")
        if max_top_k < 1:
            raise ValueError("max_top_k must be positive")
        self._dense_retriever = dense_retriever
        self._lexical_retriever = lexical_retriever
        self._candidate_multiplier = candidate_multiplier
        self._rank_constant = rank_constant
        self._max_top_k = max_top_k

    def search(
        self,
        query: str,
        document_ids: Sequence[UUID],
        top_k: int,
        score_threshold: float | None = None,
    ) -> list[RetrievalResult]:
        if not 1 <= top_k <= self._max_top_k:
            raise ValueError("top_k is outside the supported range")
        if score_threshold is not None and (
            not isfinite(score_threshold) or not 0.0 <= score_threshold <= 1.0
        ):
            raise ValueError("score_threshold must be between 0 and 1")

        candidate_limit = min(
            max(top_k, top_k * self._candidate_multiplier),
            self._max_top_k,
        )
        dense_results = self._dense_retriever.search(
            query,
            document_ids,
            candidate_limit,
            score_threshold=None,
        )
        lexical_results = self._lexical_retriever.search(
            query,
            document_ids,
            candidate_limit,
        )
        fused = reciprocal_rank_fusion(
            [dense_results, lexical_results],
            limit=top_k,
            rank_constant=self._rank_constant,
        )
        normalized = _normalize_rrf_scores(fused, self._rank_constant)
        if score_threshold is None:
            return normalized
        return [result for result in normalized if result.score >= score_threshold]


def reciprocal_rank_fusion(
    rankings: Sequence[Sequence[RetrievalResult]],
    *,
    limit: int,
    rank_constant: int = 60,
) -> list[RetrievalResult]:
    """Fuse rankings without assuming their raw scores share one scale."""

    if limit <= 0:
        raise ValueError("limit must be positive")
    if rank_constant <= 0:
        raise ValueError("rank_constant must be positive")
    if not rankings:
        return []

    results_by_chunk: dict[UUID, RetrievalResult] = {}
    fused_scores: Counter[UUID] = Counter()
    for ranking in rankings:
        seen_in_ranking: set[UUID] = set()
        for rank, result in enumerate(ranking, start=1):
            if result.chunk_id in seen_in_ranking:
                raise ValueError("a ranking cannot contain duplicate chunk IDs")
            seen_in_ranking.add(result.chunk_id)
            existing = results_by_chunk.get(result.chunk_id)
            if existing is not None and not _same_chunk(existing, result):
                raise ValueError("the same chunk ID has conflicting retrieval metadata")
            results_by_chunk[result.chunk_id] = result
            fused_scores[result.chunk_id] += 1.0 / (rank_constant + rank)

    ordered_ids = sorted(
        fused_scores,
        key=lambda chunk_id: (
            -fused_scores[chunk_id],
            *_stable_result_key(results_by_chunk[chunk_id]),
        ),
    )[:limit]
    return [
        _with_score(results_by_chunk[chunk_id], fused_scores[chunk_id])
        for chunk_id in ordered_ids
    ]


def _tokenize(text: str) -> tuple[str, ...]:
    tokens: list[str] = []
    for token in _TOKEN_PATTERN.findall(text.casefold()):
        tokens.append(token)
        if any(separator in token for separator in "-_."):
            tokens.extend(part for part in re.split(r"[-_.]", token) if part)
    return tuple(tokens)


def _same_chunk(left: RetrievalResult, right: RetrievalResult) -> bool:
    return (
        left.document_id == right.document_id
        and left.filename == right.filename
        and left.page_number == right.page_number
        and left.text == right.text
    )


def _with_score(result: RetrievalResult, score: float) -> RetrievalResult:
    return RetrievalResult(
        chunk_id=result.chunk_id,
        document_id=result.document_id,
        filename=result.filename,
        page_number=result.page_number,
        text=result.text,
        score=score,
    )


def _stable_result_key(result: RetrievalResult) -> tuple[str, int, str, str]:
    return (
        result.filename.casefold(),
        result.page_number or 0,
        " ".join(result.text.split()).casefold(),
        str(result.chunk_id),
    )


def _normalize_rrf_scores(
    results: Sequence[RetrievalResult],
    rank_constant: int,
) -> list[RetrievalResult]:
    maximum_score = 2.0 / (rank_constant + 1)
    return [
        _with_score(result, min(result.score / maximum_score, 1.0))
        for result in results
    ]
