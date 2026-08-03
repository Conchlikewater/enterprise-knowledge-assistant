"""End-to-end offline evaluation against the tracked synthetic corpus."""

from __future__ import annotations

import json
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from app.document_processing.file_validation import SUPPORTED_MEDIA_TYPES
from app.domain.models import Document
from app.services.answer_service import AnswerService, NO_EVIDENCE_ANSWER
from app.services.document_service import DocumentService
from app.services.ingestion_service import IngestionService
from app.services.retrieval_service import RetrievalService
from app.storage.qdrant_vector_store import QdrantVectorStore
from app.storage.sqlite_document_repository import SQLiteDocumentRepository
from evaluation.providers import EvaluationLLMProvider, HashingEmbeddingProvider

TOP_K = 5
UNANSWERABLE_SCORE_THRESHOLD = 0.25


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    passed: bool
    document_count: int
    txt_count: int
    pdf_count: int
    multi_page_document_count: int
    question_count: int
    category_counts: dict[str, int]
    ingested_document_count: int
    top5_source_accuracy: float
    multi_chunk_pass_rate: float
    scope_isolation_pass_rate: float
    unanswerable_rejection_rate: float
    citation_integrity_pass_rate: float
    pdf_page_metadata_pass_rate: float
    empty_chunk_invariant_passed: bool
    deletion_passed: bool
    failed_checks: tuple[str, ...]
    question_results: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_evaluation(project_root: Path | None = None) -> EvaluationReport:
    root = project_root or Path(__file__).resolve().parents[1]
    corpus_manifest = _load_json(root / "evaluation" / "corpus_sources.json")
    question_manifest = _load_json(root / "evaluation" / "questions.json")
    documents = corpus_manifest["documents"]
    questions = question_manifest["questions"]
    corpus_summary = _validate_manifests(documents, questions, root)

    with tempfile.TemporaryDirectory() as temporary_directory:
        runtime_root = Path(temporary_directory)
        repository = SQLiteDocumentRepository(runtime_root / "app.db")
        repository.initialize()
        embedding_provider = HashingEmbeddingProvider()
        llm_provider = EvaluationLLMProvider()
        vector_store = QdrantVectorStore(
            storage_path=runtime_root / "qdrant",
            collection_name="offline_evaluation_chunks",
            vector_size=embedding_provider.dimensions,
        )
        vector_store.initialize()
        try:
            ingestion_service = IngestionService(
                document_repository=repository,
                vector_store=vector_store,
                embedding_provider=embedding_provider,
                upload_dir=runtime_root / "uploads",
                max_upload_bytes=2 * 1024 * 1024,
                chunk_size=220,
                chunk_overlap=30,
            )
            retrieval_service = RetrievalService(
                document_repository=repository,
                vector_store=vector_store,
                embedding_provider=embedding_provider,
            )
            answer_service = AnswerService(retrieval_service, llm_provider)
            document_service = DocumentService(
                document_repository=repository,
                vector_store=vector_store,
                upload_dir=runtime_root / "uploads",
            )

            ingested: dict[str, Document] = {}
            for document_spec in documents:
                source_path = root / "evaluation" / "documents" / document_spec["filename"]
                with source_path.open("rb") as source:
                    ingested_document = ingestion_service.ingest(
                        source,
                        filename=document_spec["filename"],
                        media_type=document_spec["media_type"],
                    )
                ingested[document_spec["filename"]] = ingested_document

            metrics = _evaluate_questions(
                questions,
                ingested,
                retrieval_service,
                answer_service,
            )
            empty_chunk_invariant = all(
                document.chunk_count > 0 for document in ingested.values()
            )
            deletion_passed = _evaluate_deletion(
                document_service,
                repository,
                vector_store,
                embedding_provider,
                ingested["access_policy.txt"],
            )
        finally:
            try:
                llm_provider.close()
                embedding_provider.close()
            finally:
                vector_store.close()

    checks = {
        "document_count": corpus_summary["document_count"] == 10,
        "txt_count": corpus_summary["txt_count"] >= 4,
        "pdf_count": corpus_summary["pdf_count"] >= 4,
        "multi_page_document_count": corpus_summary["multi_page_document_count"] >= 2,
        "question_count": corpus_summary["question_count"] == 20,
        "category_distribution": corpus_summary["category_counts"]
        == {
            "direct": 10,
            "multi_chunk": 4,
            "scope_isolation": 2,
            "unanswerable": 4,
        },
        "all_documents_ingested": len(ingested) == 10,
        "top5_source_accuracy": metrics["top5_source_accuracy"] >= 0.80,
        "multi_chunk_pass_rate": metrics["multi_chunk_pass_rate"] == 1.0,
        "scope_isolation_pass_rate": metrics["scope_isolation_pass_rate"] == 1.0,
        "unanswerable_rejection_rate": metrics["unanswerable_rejection_rate"] == 1.0,
        "citation_integrity_pass_rate": metrics["citation_integrity_pass_rate"] == 1.0,
        "pdf_page_metadata_pass_rate": metrics["pdf_page_metadata_pass_rate"] == 1.0,
        "empty_chunk_invariant": empty_chunk_invariant,
        "deletion": deletion_passed,
    }
    failed_checks = tuple(name for name, passed in checks.items() if not passed)
    return EvaluationReport(
        passed=not failed_checks,
        document_count=corpus_summary["document_count"],
        txt_count=corpus_summary["txt_count"],
        pdf_count=corpus_summary["pdf_count"],
        multi_page_document_count=corpus_summary["multi_page_document_count"],
        question_count=corpus_summary["question_count"],
        category_counts=corpus_summary["category_counts"],
        ingested_document_count=len(ingested),
        top5_source_accuracy=metrics["top5_source_accuracy"],
        multi_chunk_pass_rate=metrics["multi_chunk_pass_rate"],
        scope_isolation_pass_rate=metrics["scope_isolation_pass_rate"],
        unanswerable_rejection_rate=metrics["unanswerable_rejection_rate"],
        citation_integrity_pass_rate=metrics["citation_integrity_pass_rate"],
        pdf_page_metadata_pass_rate=metrics["pdf_page_metadata_pass_rate"],
        empty_chunk_invariant_passed=empty_chunk_invariant,
        deletion_passed=deletion_passed,
        failed_checks=failed_checks,
        question_results=metrics["question_results"],
    )


def _evaluate_questions(
    questions: list[dict[str, Any]],
    ingested: dict[str, Document],
    retrieval_service: RetrievalService,
    answer_service: AnswerService,
) -> dict[str, Any]:
    all_document_ids = [document.document_id for document in ingested.values()]
    counters = {
        "answerable": 0,
        "top5": 0,
        "multi": 0,
        "multi_pass": 0,
        "scope": 0,
        "scope_pass": 0,
        "unanswerable": 0,
        "unanswerable_pass": 0,
        "citation": 0,
        "citation_pass": 0,
        "pages": 0,
        "pages_pass": 0,
    }
    question_results: list[dict[str, Any]] = []

    for question in questions:
        scope_names = question["scope"]
        scope_ids = (
            all_document_ids
            if scope_names == ["*"]
            else [ingested[name].document_id for name in scope_names]
        )
        threshold = (
            UNANSWERABLE_SCORE_THRESHOLD
            if question["category"] == "unanswerable"
            else None
        )
        results = retrieval_service.search(
            question["question"],
            scope_ids,
            top_k=TOP_K,
            score_threshold=threshold,
        )
        answer = answer_service.answer(
            question["question"],
            scope_ids,
            top_k=TOP_K,
            score_threshold=threshold,
        )
        retrieved_sources = {result.filename for result in results}
        expected_sources = set(question["expected_sources"])
        source_pass = expected_sources.issubset(retrieved_sources)
        reasons: list[str] = []

        if question["category"] != "unanswerable":
            counters["answerable"] += 1
            counters["top5"] += int(source_pass)
            if not source_pass:
                reasons.append("expected_source_missing")

            result_keys = {
                (
                    result.chunk_id,
                    result.document_id,
                    result.filename,
                    result.page_number,
                )
                for result in results
            }
            citation_pass = len(answer.citations) == len(results) and all(
                (
                    citation.chunk_id,
                    citation.document_id,
                    citation.filename,
                    citation.page_number,
                )
                in result_keys
                for citation in answer.citations
            )
            counters["citation"] += 1
            counters["citation_pass"] += int(citation_pass)
            if not citation_pass:
                reasons.append("citation_mismatch")

        if question["category"] == "multi_chunk":
            counters["multi"] += 1
            expected_chunk_count = question["minimum_expected_chunks"]
            matching_chunks = sum(
                result.filename in expected_sources for result in results
            )
            multi_pass = matching_chunks >= expected_chunk_count
            counters["multi_pass"] += int(multi_pass)
            if not multi_pass:
                reasons.append("insufficient_expected_chunks")

        if question["category"] == "scope_isolation":
            counters["scope"] += 1
            scope_pass = all(result.filename in scope_names for result in results)
            counters["scope_pass"] += int(scope_pass)
            if not scope_pass:
                reasons.append("out_of_scope_result")

        if question["category"] == "unanswerable":
            counters["unanswerable"] += 1
            unanswerable_pass = (
                not results
                and not answer.citations
                and answer.answer == NO_EVIDENCE_ANSWER
            )
            counters["unanswerable_pass"] += int(unanswerable_pass)
            if not unanswerable_pass:
                reasons.append("unsupported_answer")

        if expected_pages := question.get("expected_pages"):
            counters["pages"] += 1
            retrieved_pages = {
                result.page_number
                for result in results
                if result.filename in expected_sources
            }
            page_pass = set(expected_pages).issubset(retrieved_pages)
            counters["pages_pass"] += int(page_pass)
            if not page_pass:
                reasons.append("expected_page_missing")

        question_results.append(
            {
                "id": question["id"],
                "category": question["category"],
                "passed": not reasons,
                "retrieved_sources": sorted(retrieved_sources),
                "result_count": len(results),
                "results": [
                    {
                        "filename": result.filename,
                        "page_number": result.page_number,
                        "score": round(result.score, 4),
                    }
                    for result in results
                ],
                "failures": reasons,
            }
        )

    return {
        "top5_source_accuracy": _rate(counters["top5"], counters["answerable"]),
        "multi_chunk_pass_rate": _rate(counters["multi_pass"], counters["multi"]),
        "scope_isolation_pass_rate": _rate(counters["scope_pass"], counters["scope"]),
        "unanswerable_rejection_rate": _rate(
            counters["unanswerable_pass"], counters["unanswerable"]
        ),
        "citation_integrity_pass_rate": _rate(
            counters["citation_pass"], counters["citation"]
        ),
        "pdf_page_metadata_pass_rate": _rate(
            counters["pages_pass"], counters["pages"]
        ),
        "question_results": tuple(question_results),
    }


def _evaluate_deletion(
    document_service: DocumentService,
    repository: SQLiteDocumentRepository,
    vector_store: QdrantVectorStore,
    embedding_provider: HashingEmbeddingProvider,
    document: Document,
) -> bool:
    stored_path = document.stored_path
    document_service.delete_document(document.document_id)
    remaining = vector_store.search(
        embedding_provider.embed_query("privileged access recertification"),
        [document.document_id],
        limit=TOP_K,
    )
    return (
        repository.get(document.document_id) is None
        and not stored_path.exists()
        and not remaining
    )


def _validate_manifests(
    documents: list[dict[str, Any]],
    questions: list[dict[str, Any]],
    root: Path,
) -> dict[str, Any]:
    filenames = [document["filename"] for document in documents]
    if len(filenames) != len(set(filenames)):
        raise ValueError("evaluation document filenames must be unique")
    question_ids = [question["id"] for question in questions]
    if len(question_ids) != len(set(question_ids)):
        raise ValueError("evaluation question IDs must be unique")

    known_filenames = set(filenames)
    for document in documents:
        expected_media_type = SUPPORTED_MEDIA_TYPES.get(
            Path(document["filename"]).suffix.lower()
        )
        if document["media_type"] != expected_media_type:
            raise ValueError("fixture extension and media type must agree")
        if not (root / "evaluation" / "documents" / document["filename"]).is_file():
            raise ValueError(f"missing generated fixture: {document['filename']}")

    for question in questions:
        scope = question["scope"]
        if scope != ["*"] and not set(scope).issubset(known_filenames):
            raise ValueError(f"unknown scope document in {question['id']}")
        if not set(question["expected_sources"]).issubset(known_filenames):
            raise ValueError(f"unknown expected source in {question['id']}")

    category_counts: dict[str, int] = {}
    for question in questions:
        category = question["category"]
        category_counts[category] = category_counts.get(category, 0) + 1

    return {
        "document_count": len(documents),
        "txt_count": sum(item["media_type"] == "text/plain" for item in documents),
        "pdf_count": sum(
            item["media_type"] == "application/pdf" for item in documents
        ),
        "multi_page_document_count": sum(
            len(item["pages"]) > 1 for item in documents
        ),
        "question_count": len(questions),
        "category_counts": category_counts,
    }


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _rate(passed: int, total: int) -> float:
    return round(passed / total, 4) if total else 0.0
