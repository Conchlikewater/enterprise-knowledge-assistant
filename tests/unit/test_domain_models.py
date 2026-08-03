import unittest
from math import nan
from uuid import uuid4

from app.domain.models import Citation, Chunk, RetrievalResult


class DomainModelTests(unittest.TestCase):
    def test_empty_chunk_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            Chunk(
                chunk_id=uuid4(),
                document_id=uuid4(),
                chunk_index=0,
                text="   ",
                filename="notes.txt",
                content_hash="hash",
            )

    def test_citation_uses_retrieved_metadata(self) -> None:
        result = RetrievalResult(
            chunk_id=uuid4(),
            document_id=uuid4(),
            filename="policy.pdf",
            page_number=3,
            text="Evidence   from\n the selected document.",
            score=0.91,
        )

        citation = Citation.from_result(result, citation_number=1)

        self.assertEqual(citation.document_id, result.document_id)
        self.assertEqual(citation.chunk_id, result.chunk_id)
        self.assertEqual(citation.page_number, 3)
        self.assertEqual(citation.excerpt, "Evidence from the selected document.")

    def test_invalid_retrieval_result_is_rejected(self) -> None:
        cases = (
            {"filename": "", "text": "evidence", "score": 0.5},
            {"filename": "notes.txt", "text": "   ", "score": 0.5},
            {"filename": "notes.txt", "text": "evidence", "score": nan},
        )

        for values in cases:
            with self.subTest(values=values):
                with self.assertRaises(ValueError):
                    RetrievalResult(
                        chunk_id=uuid4(),
                        document_id=uuid4(),
                        **values,
                    )


if __name__ == "__main__":
    unittest.main()
