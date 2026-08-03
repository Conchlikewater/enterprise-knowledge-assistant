import tempfile
import unittest
from hashlib import sha256
from pathlib import Path
from uuid import UUID, uuid4

from app.core.exceptions import VectorStoreError
from app.domain.models import Chunk
from app.storage.qdrant_vector_store import QdrantVectorStore


class QdrantVectorStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary_directory.cleanup)
        self.storage_path = Path(self._temporary_directory.name) / "qdrant"
        self.store = self._new_store()
        self.store.initialize()

    def tearDown(self) -> None:
        self.store.close()

    def _new_store(self, vector_size: int = 3) -> QdrantVectorStore:
        return QdrantVectorStore(
            storage_path=self.storage_path,
            collection_name="test_chunks",
            vector_size=vector_size,
        )

    @staticmethod
    def _chunk(
        document_id: UUID,
        chunk_index: int,
        text: str,
        page_number: int | None = None,
    ) -> Chunk:
        return Chunk(
            chunk_id=uuid4(),
            document_id=document_id,
            chunk_index=chunk_index,
            text=text,
            filename=f"{document_id}.txt",
            page_number=page_number,
            content_hash=sha256(text.encode("utf-8")).hexdigest(),
        )

    def test_initialize_creates_a_healthy_collection(self) -> None:
        self.assertTrue(self.store.health())

        self.store.initialize()
        self.assertTrue(self.store.health())

        self.store.close()
        self.assertFalse(self.store.health())

    def test_search_is_document_scoped_and_score_ordered(self) -> None:
        selected_document = uuid4()
        excluded_document = uuid4()
        selected_best = self._chunk(selected_document, 0, "selected best", page_number=2)
        selected_second = self._chunk(selected_document, 1, "selected second")
        excluded = self._chunk(excluded_document, 0, "excluded perfect match")
        self.store.upsert(
            [selected_best, selected_second, excluded],
            [[1.0, 0.0, 0.0], [0.8, 0.2, 0.0], [1.0, 0.0, 0.0]],
        )

        results = self.store.search([1.0, 0.0, 0.0], [selected_document], limit=10)

        self.assertEqual([result.chunk_id for result in results], [selected_best.chunk_id, selected_second.chunk_id])
        self.assertTrue(all(result.document_id == selected_document for result in results))
        self.assertEqual(results[0].page_number, 2)
        self.assertGreaterEqual(results[0].score, results[1].score)

    def test_multi_document_scope_and_delete(self) -> None:
        first_document = uuid4()
        second_document = uuid4()
        first_chunk = self._chunk(first_document, 0, "first")
        second_chunk = self._chunk(second_document, 0, "second")
        self.store.upsert(
            [first_chunk, second_chunk],
            [[1.0, 0.0, 0.0], [0.9, 0.1, 0.0]],
        )

        before_delete = self.store.search(
            [1.0, 0.0, 0.0], [first_document, second_document], limit=10
        )
        self.assertEqual(len(before_delete), 2)

        self.store.delete_by_document(first_document)

        self.assertEqual(
            self.store.search([1.0, 0.0, 0.0], [first_document], limit=10),
            [],
        )
        remaining = self.store.search(
            [1.0, 0.0, 0.0], [second_document], limit=10
        )
        self.assertEqual([result.chunk_id for result in remaining], [second_chunk.chunk_id])

    def test_points_persist_after_reopening_local_storage(self) -> None:
        document_id = uuid4()
        chunk = self._chunk(document_id, 0, "persistent evidence")
        self.store.upsert([chunk], [[0.0, 1.0, 0.0]])
        self.store.close()

        self.store = self._new_store()
        self.store.initialize()
        results = self.store.search([0.0, 1.0, 0.0], [document_id], limit=1)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].chunk_id, chunk.chunk_id)
        self.assertEqual(results[0].text, "persistent evidence")

    def test_invalid_vectors_and_empty_scope_are_rejected(self) -> None:
        document_id = uuid4()
        chunk = self._chunk(document_id, 0, "evidence")

        with self.assertRaises(ValueError):
            self.store.upsert([chunk], [])
        with self.assertRaises(ValueError):
            self.store.upsert([chunk], [[1.0, 0.0]])
        with self.assertRaises(ValueError):
            self.store.search([1.0, 0.0, 0.0], [], limit=5)
        with self.assertRaises(ValueError):
            self.store.search([float("nan"), 0.0, 0.0], [document_id], limit=5)

    def test_existing_collection_dimension_mismatch_is_safe(self) -> None:
        self.store.close()
        self.store = self._new_store(vector_size=4)

        with self.assertRaises(VectorStoreError):
            self.store.initialize()


if __name__ == "__main__":
    unittest.main()
