import tempfile
import unittest
from collections.abc import Sequence
from pathlib import Path
from uuid import UUID, uuid4

from app.core.exceptions import (
    DocumentNotFoundError,
    DocumentNotReadyError,
    VectorStoreError,
)
from app.domain.models import Chunk, Document, DocumentStatus, RetrievalResult
from app.services.retrieval_service import RetrievalService
from app.storage.sqlite_document_repository import SQLiteDocumentRepository
from app.storage.vector_store import VectorStore
from tests.fakes import DeterministicEmbeddingProvider


class RecordingSearchVectorStore(VectorStore):
    def __init__(self) -> None:
        self.results: list[RetrievalResult] = []
        self.search_calls: list[tuple[list[float], tuple[UUID, ...], int]] = []

    @property
    def dimensions(self) -> int:
        return 3

    def initialize(self) -> None:
        pass

    def health(self) -> bool:
        return True

    def upsert(
        self,
        chunks: Sequence[Chunk],
        vectors: Sequence[Sequence[float]],
    ) -> None:
        raise NotImplementedError

    def search(
        self,
        query_vector: Sequence[float],
        document_ids: Sequence[UUID],
        limit: int,
    ) -> list[RetrievalResult]:
        self.search_calls.append((list(query_vector), tuple(document_ids), limit))
        return list(self.results)

    def delete_by_document(self, document_id: UUID) -> None:
        raise NotImplementedError

    def close(self) -> None:
        pass


class RetrievalServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary_directory.cleanup)
        self.root = Path(self._temporary_directory.name)
        self.repository = SQLiteDocumentRepository(self.root / "app.db")
        self.repository.initialize()
        self.vector_store = RecordingSearchVectorStore()
        self.provider = DeterministicEmbeddingProvider()
        self.service = RetrievalService(
            document_repository=self.repository,
            vector_store=self.vector_store,
            embedding_provider=self.provider,
        )

    def test_search_is_scoped_sorted_filtered_and_privacy_safe(self) -> None:
        first_document = self._create_document(DocumentStatus.READY)
        second_document = self._create_document(
            DocumentStatus.READY,
            sha256="b" * 64,
        )
        low_score = self._result(first_document.document_id, score=0.4)
        high_score = self._result(second_document.document_id, score=0.9)
        self.vector_store.results = [low_score, high_score]
        private_query = "  INTERNAL_QUERY_MARKER quarterly review  "

        with self.assertLogs("app.services.retrieval_service", level="INFO") as logs:
            results = self.service.search(
                private_query,
                [first_document.document_id, second_document.document_id],
                top_k=7,
                score_threshold=0.5,
            )

        self.assertEqual(results, [high_score])
        self.assertEqual(
            self.provider.embedded_queries,
            ["INTERNAL_QUERY_MARKER quarterly review"],
        )
        self.assertEqual(
            self.vector_store.search_calls[0][1:],
            ((first_document.document_id, second_document.document_id), 7),
        )
        self.assertNotIn(private_query.strip(), "\n".join(logs.output))

    def test_missing_or_unready_document_stops_before_embedding(self) -> None:
        failed_document = self._create_document(DocumentStatus.FAILED)
        cases = (
            (uuid4(), DocumentNotFoundError),
            (failed_document.document_id, DocumentNotReadyError),
        )

        for document_id, expected_error in cases:
            with self.subTest(expected_error=expected_error.__name__):
                with self.assertRaises(expected_error):
                    self.service.search("safe query", [document_id], top_k=5)

        self.assertEqual(self.provider.embedded_queries, [])
        self.assertEqual(self.vector_store.search_calls, [])

    def test_out_of_scope_adapter_result_is_rejected(self) -> None:
        selected_document = self._create_document(DocumentStatus.READY)
        self.vector_store.results = [self._result(uuid4(), score=1.0)]

        with self.assertRaises(VectorStoreError):
            self.service.search(
                "safe query",
                [selected_document.document_id],
                top_k=5,
            )

    def test_score_threshold_can_return_an_explicit_no_evidence_result(self) -> None:
        selected_document = self._create_document(DocumentStatus.READY)
        self.vector_store.results = [
            self._result(selected_document.document_id, score=0.2)
        ]

        results = self.service.search(
            "safe query",
            [selected_document.document_id],
            top_k=5,
            score_threshold=0.8,
        )

        self.assertEqual(results, [])

    def test_adapter_cannot_return_more_than_top_k_results(self) -> None:
        selected_document = self._create_document(DocumentStatus.READY)
        best = self._result(selected_document.document_id, score=0.9)
        extra = self._result(selected_document.document_id, score=0.8)
        self.vector_store.results = [extra, best]

        results = self.service.search(
            "safe query",
            [selected_document.document_id],
            top_k=1,
        )

        self.assertEqual(results, [best])

    def test_invalid_direct_service_requests_are_rejected(self) -> None:
        ready_document = self._create_document(DocumentStatus.READY)
        cases = (
            ("", [ready_document.document_id], 5, None),
            ("x" * 4001, [ready_document.document_id], 5, None),
            ("query", [], 5, None),
            (
                "query",
                [ready_document.document_id, ready_document.document_id],
                5,
                None,
            ),
            ("query", [ready_document.document_id], 0, None),
            ("query", [ready_document.document_id], 5, 1.1),
        )

        for query, document_ids, top_k, threshold in cases:
            with self.subTest(
                document_count=len(document_ids),
                top_k=top_k,
                threshold=threshold,
            ):
                with self.assertRaises(ValueError):
                    self.service.search(query, document_ids, top_k, threshold)

    def _create_document(
        self,
        status: DocumentStatus,
        sha256: str = "a" * 64,
    ) -> Document:
        document_id = uuid4()
        document = Document(
            document_id=document_id,
            filename=f"{document_id}.txt",
            media_type="text/plain",
            size_bytes=20,
            sha256=sha256,
            status=status,
            stored_path=self.root / f"{document_id}.txt",
            chunk_count=1 if status is DocumentStatus.READY else 0,
        )
        self.repository.create(document)
        return document

    @staticmethod
    def _result(document_id: UUID, score: float) -> RetrievalResult:
        return RetrievalResult(
            chunk_id=uuid4(),
            document_id=document_id,
            filename=f"{document_id}.txt",
            text="retrieved evidence",
            score=score,
        )


if __name__ == "__main__":
    unittest.main()
