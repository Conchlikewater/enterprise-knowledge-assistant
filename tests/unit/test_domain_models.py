import unittest
from datetime import UTC, datetime
from math import nan
from uuid import uuid4

from app.domain.models import (
    AnswerResult,
    Chunk,
    Citation,
    IngestionJob,
    IngestionJobStatus,
    RetrievalResult,
)


class DomainModelTests(unittest.TestCase):
    def test_ingestion_job_requires_state_consistent_metadata(self) -> None:
        now = datetime.now(UTC)
        with self.assertRaises(ValueError):
            IngestionJob(
                job_id=uuid4(),
                document_id=uuid4(),
                status=IngestionJobStatus.RUNNING,
            )
        with self.assertRaises(ValueError):
            IngestionJob(
                job_id=uuid4(),
                document_id=uuid4(),
                status=IngestionJobStatus.PENDING,
                started_at=now,
            )
        with self.assertRaises(ValueError):
            IngestionJob(
                job_id=uuid4(),
                document_id=uuid4(),
                status=IngestionJobStatus.RUNNING,
                started_at=now,
                completed_at=now,
            )
        with self.assertRaises(ValueError):
            IngestionJob(
                job_id=uuid4(),
                document_id=uuid4(),
                status=IngestionJobStatus.FAILED,
                completed_at=now,
                error_code="INGESTION_FAILED",
            )

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

    def test_answer_result_rejects_more_citations_than_retrievals(self) -> None:
        result = RetrievalResult(
            chunk_id=uuid4(),
            document_id=uuid4(),
            filename="policy.txt",
            text="evidence",
            score=0.8,
        )
        citation = Citation.from_result(result, citation_number=1)

        with self.assertRaises(ValueError):
            AnswerResult(
                answer="answer",
                citations=(citation,),
                retrieval_count=0,
            )


if __name__ == "__main__":
    unittest.main()
