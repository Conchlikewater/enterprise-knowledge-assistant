"""Local persistent Qdrant implementation of the vector store port."""

from __future__ import annotations

from collections.abc import Sequence
from math import isfinite
from pathlib import Path
from uuid import UUID

from qdrant_client import QdrantClient, models

from app.core.exceptions import VectorStoreError
from app.domain.models import Chunk, RetrievalResult
from app.storage.vector_store import VectorStore


class QdrantVectorStore(VectorStore):
    def __init__(
        self,
        storage_path: Path,
        collection_name: str,
        vector_size: int,
    ) -> None:
        if not collection_name.strip():
            raise ValueError("collection_name must not be empty")
        if vector_size <= 0:
            raise ValueError("vector_size must be positive")
        self._storage_path = storage_path
        self._collection_name = collection_name
        self._vector_size = vector_size
        self._client: QdrantClient | None = None

    @property
    def dimensions(self) -> int:
        return self._vector_size

    def initialize(self) -> None:
        if self._client is not None:
            self._validate_collection(self._client)
            return
        try:
            self._storage_path.mkdir(parents=True, exist_ok=True)
            client = QdrantClient(path=str(self._storage_path))
            self._client = client
            if client.collection_exists(self._collection_name):
                self._validate_collection(client)
            else:
                client.create_collection(
                    collection_name=self._collection_name,
                    vectors_config=models.VectorParams(
                        size=self._vector_size,
                        distance=models.Distance.COSINE,
                    ),
                )
        except VectorStoreError:
            self.close()
            raise
        except Exception as exc:
            self.close()
            raise VectorStoreError() from exc

    def health(self) -> bool:
        if self._client is None:
            return False
        try:
            return self._client.collection_exists(self._collection_name)
        except Exception:
            return False

    def upsert(self, chunks: Sequence[Chunk], vectors: Sequence[Sequence[float]]) -> None:
        if len(chunks) != len(vectors):
            raise ValueError("chunks and vectors must have the same length")
        if not chunks:
            return

        normalized_vectors = [self._validate_vector(vector) for vector in vectors]
        points = [
            models.PointStruct(
                id=chunk.chunk_id,
                vector=vector,
                payload={
                    "chunk_id": str(chunk.chunk_id),
                    "document_id": str(chunk.document_id),
                    "chunk_index": chunk.chunk_index,
                    "text": chunk.text,
                    "filename": chunk.filename,
                    "page_number": chunk.page_number,
                    "content_hash": chunk.content_hash,
                },
            )
            for chunk, vector in zip(chunks, normalized_vectors, strict=True)
        ]
        try:
            self._require_client().upsert(
                collection_name=self._collection_name,
                points=points,
                wait=True,
            )
        except Exception as exc:
            raise VectorStoreError() from exc

    def search(
        self,
        query_vector: Sequence[float],
        document_ids: Sequence[UUID],
        limit: int,
    ) -> list[RetrievalResult]:
        if not document_ids:
            raise ValueError("document_ids must not be empty")
        if limit <= 0:
            raise ValueError("limit must be positive")
        normalized_query = self._validate_vector(query_vector)
        document_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="document_id",
                    match=models.MatchAny(any=[str(value) for value in document_ids]),
                )
            ]
        )

        try:
            response = self._require_client().query_points(
                collection_name=self._collection_name,
                query=normalized_query,
                query_filter=document_filter,
                limit=limit,
                with_payload=True,
                with_vectors=False,
            )
            return [self._to_retrieval_result(point) for point in response.points]
        except VectorStoreError:
            raise
        except Exception as exc:
            raise VectorStoreError() from exc

    def delete_by_document(self, document_id: UUID) -> None:
        document_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="document_id",
                    match=models.MatchValue(value=str(document_id)),
                )
            ]
        )
        try:
            self._require_client().delete(
                collection_name=self._collection_name,
                points_selector=models.FilterSelector(filter=document_filter),
                wait=True,
            )
        except Exception as exc:
            raise VectorStoreError() from exc

    def close(self) -> None:
        if self._client is not None:
            try:
                self._client.close()
            finally:
                self._client = None

    def _validate_collection(self, client: QdrantClient) -> None:
        collection = client.get_collection(self._collection_name)
        vector_config = collection.config.params.vectors
        if (
            not isinstance(vector_config, models.VectorParams)
            or vector_config.size != self._vector_size
            or vector_config.distance != models.Distance.COSINE
        ):
            raise VectorStoreError()

    def _require_client(self) -> QdrantClient:
        if self._client is None:
            raise VectorStoreError()
        return self._client

    def _validate_vector(self, vector: Sequence[float]) -> list[float]:
        if len(vector) != self._vector_size:
            raise ValueError(
                f"vector must contain exactly {self._vector_size} dimensions"
            )
        normalized = [float(value) for value in vector]
        if not all(isfinite(value) for value in normalized):
            raise ValueError("vector values must be finite")
        return normalized

    @staticmethod
    def _to_retrieval_result(point: models.ScoredPoint) -> RetrievalResult:
        payload = point.payload or {}
        try:
            return RetrievalResult(
                chunk_id=UUID(str(payload["chunk_id"])),
                document_id=UUID(str(payload["document_id"])),
                filename=str(payload["filename"]),
                page_number=(
                    int(payload["page_number"])
                    if payload.get("page_number") is not None
                    else None
                ),
                text=str(payload["text"]),
                score=float(point.score),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise VectorStoreError() from exc
