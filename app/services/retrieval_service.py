"""Document-scoped semantic retrieval orchestration."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from math import isfinite
from time import monotonic
from uuid import UUID

from app.core.exceptions import (
    DocumentNotFoundError,
    DocumentNotReadyError,
    VectorStoreError,
)
from app.domain.models import DocumentStatus, RetrievalResult
from app.providers.embedding_provider import EmbeddingProvider
from app.storage.document_repository import DocumentRepository
from app.storage.vector_store import VectorStore

logger = logging.getLogger(__name__)


class RetrievalService:
    def __init__(
        self,
        document_repository: DocumentRepository,
        vector_store: VectorStore,
        embedding_provider: EmbeddingProvider,
        max_query_characters: int = 4000,
        max_selected_documents: int = 50,
        max_top_k: int = 50,
    ) -> None:
        if embedding_provider.dimensions != vector_store.dimensions:
            raise ValueError("embedding and vector store dimensions must match")
        if max_query_characters <= 0:
            raise ValueError("max_query_characters must be positive")
        if max_selected_documents <= 0:
            raise ValueError("max_selected_documents must be positive")
        if max_top_k <= 0:
            raise ValueError("max_top_k must be positive")

        self._document_repository = document_repository
        self._vector_store = vector_store
        self._embedding_provider = embedding_provider
        self._max_query_characters = max_query_characters
        self._max_selected_documents = max_selected_documents
        self._max_top_k = max_top_k

    def search(
        self,
        query: str,
        document_ids: Sequence[UUID],
        top_k: int,
        score_threshold: float | None = None,
    ) -> list[RetrievalResult]:
        started_at = monotonic()
        selected_ids = list(document_ids)
        try:
            normalized_query = self._validate_request(
                query,
                selected_ids,
                top_k,
                score_threshold,
            )
            self._validate_documents(selected_ids)
            query_vector = self._embedding_provider.embed_query(normalized_query)
            results = self._vector_store.search(
                query_vector=query_vector,
                document_ids=selected_ids,
                limit=top_k,
            )
            allowed_document_ids = set(selected_ids)
            if any(
                result.document_id not in allowed_document_ids for result in results
            ):
                raise VectorStoreError()

            ordered_results = sorted(
                results,
                key=lambda result: result.score,
                reverse=True,
            )[:top_k]
            if score_threshold is not None:
                ordered_results = [
                    result
                    for result in ordered_results
                    if result.score >= score_threshold
                ]

            logger.info(
                "retrieval_succeeded provider=%s selected_document_count=%d "
                "result_count=%d top_k=%d elapsed_ms=%d",
                self._embedding_provider.name,
                len(selected_ids),
                len(ordered_results),
                top_k,
                int((monotonic() - started_at) * 1000),
            )
            return ordered_results
        except Exception as exc:
            logger.warning(
                "retrieval_failed provider=%s selected_document_count=%d "
                "error_type=%s elapsed_ms=%d",
                self._embedding_provider.name,
                len(selected_ids),
                type(exc).__name__,
                int((monotonic() - started_at) * 1000),
            )
            raise

    def _validate_request(
        self,
        query: str,
        document_ids: list[UUID],
        top_k: int,
        score_threshold: float | None,
    ) -> str:
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must not be empty")
        if len(query.strip()) > self._max_query_characters:
            raise ValueError("query is too long")
        if not document_ids:
            raise ValueError("document_ids must not be empty")
        if len(document_ids) > self._max_selected_documents:
            raise ValueError("too many document_ids")
        if len(set(document_ids)) != len(document_ids):
            raise ValueError("document_ids must be unique")
        if not 1 <= top_k <= self._max_top_k:
            raise ValueError("top_k is outside the supported range")
        if score_threshold is not None and (
            not isfinite(score_threshold) or not -1.0 <= score_threshold <= 1.0
        ):
            raise ValueError("score_threshold must be between -1 and 1")
        return query.strip()

    def _validate_documents(self, document_ids: Sequence[UUID]) -> None:
        for document_id in document_ids:
            document = self._document_repository.get(document_id)
            if document is None:
                raise DocumentNotFoundError()
            if document.status is not DocumentStatus.READY:
                raise DocumentNotReadyError()
