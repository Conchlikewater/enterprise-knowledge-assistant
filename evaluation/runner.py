"""End-to-end offline evaluation against the tracked synthetic corpus."""

from __future__ import annotations

import json
import tempfile
from collections.abc import Callable, Iterable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter
from typing import Any, Protocol
from uuid import UUID

from app.document_processing.file_validation import SUPPORTED_MEDIA_TYPES
from app.domain.models import Document, RetrievalResult
from app.providers.embedding_provider import EmbeddingProvider
from app.services.answer_service import NO_EVIDENCE_ANSWER, AnswerService
from app.services.document_service import DocumentService
from app.services.ingestion_service import IngestionService
from app.services.retrieval_service import RetrievalService
from app.storage.qdrant_vector_store import QdrantVectorStore
from app.storage.sqlite_document_repository import SQLiteDocumentRepository
from app.storage.vector_store import VectorStore
from evaluation.contracts import (
    EvaluationQuestion,
    ExpectedEvidence,
    load_question_contracts,
)
from evaluation.metrics import hit_rate_at_k, mean_reciprocal_rank, recall_at_k
from evaluation.providers import EvaluationLLMProvider, HashingEmbeddingProvider

EmbeddingProviderFactory = Callable[[], EmbeddingProvider]


class SearchService(Protocol):
    """Structural contract shared by dense and experimental retrievers."""

    def search(
        self,
        query: str,
        document_ids: Sequence[UUID],
        top_k: int,
        score_threshold: float | None = None,
    ) -> list[RetrievalResult]: ...


VectorStoreWrapper = Callable[[VectorStore], VectorStore]
SearchServiceFactory = Callable[
    [SQLiteDocumentRepository, VectorStore, EmbeddingProvider], SearchService
]
QuestionTimingObserver = Callable[[EvaluationQuestion, float, float], None]

TOP_K = 5
CHUNK_SIZE = 220
CHUNK_OVERLAP = 30
UNANSWERABLE_SCORE_THRESHOLD = 0.25
AMBIGUITY_SCORE_MARGIN = 0.05
MIN_EVIDENCE_HIT_RATE = 0.80
MIN_EVIDENCE_RECALL = 0.80
MIN_EVIDENCE_MRR = 0.75
MIN_UNANSWERABLE_REJECTION_RATE = 0.85


@dataclass(frozen=True, slots=True)
class EvaluationConfig:
    """Tunable inputs for one isolated offline evaluation run."""

    name: str = "baseline"
    chunk_size: int = CHUNK_SIZE
    chunk_overlap: int = CHUNK_OVERLAP
    top_k: int = TOP_K
    unanswerable_score_threshold: float = UNANSWERABLE_SCORE_THRESHOLD
    ambiguity_score_margin: float = AMBIGUITY_SCORE_MARGIN

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("evaluation config name must not be empty")
        if self.chunk_size < 1:
            raise ValueError("chunk_size must be positive")
        if self.chunk_overlap < 0 or self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be non-negative and below chunk_size")
        if self.top_k < 1 or self.top_k > 50:
            raise ValueError("top_k must be between 1 and 50")
        if not 0.0 <= self.unanswerable_score_threshold <= 1.0:
            raise ValueError("unanswerable_score_threshold must be between 0 and 1")
        if not 0.0 <= self.ambiguity_score_margin <= 1.0:
            raise ValueError("ambiguity_score_margin must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class EvaluationProfile:
    """Configuration that makes an offline baseline reproducible."""

    name: str
    corpus: str
    embedding_provider: str
    embedding_model: str | None
    embedding_dimensions: int
    llm_provider: str
    llm_model: str
    chunk_size: int
    chunk_overlap: int
    top_k: int
    answerable_score_threshold: float | None
    unanswerable_score_threshold: float
    ambiguity_score_margin: float
    minimum_evidence_hit_rate: float
    minimum_evidence_recall: float
    minimum_evidence_mrr: float
    minimum_unanswerable_rejection_rate: float


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    passed: bool
    profile: EvaluationProfile
    document_count: int
    txt_count: int
    pdf_count: int
    multi_page_document_count: int
    question_count: int
    category_counts: dict[str, int]
    category_metrics: dict[str, dict[str, Any]]
    ingested_document_count: int
    source_hit_rate_at_k: float
    evidence_hit_rate_at_k: float
    evidence_recall_at_k: float
    evidence_mean_reciprocal_rank: float
    clarification_candidate_recall_at_k: float
    clarification_response_rate: float
    multi_chunk_pass_rate: float
    scope_isolation_pass_rate: float
    unanswerable_rejection_rate: float
    citation_integrity_pass_rate: float
    pdf_page_metadata_pass_rate: float
    empty_chunk_invariant_passed: bool
    deletion_passed: bool
    bad_case_count: int
    failed_checks: tuple[str, ...]
    question_results: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["failed_checks"] = list(self.failed_checks)
        payload["question_results"] = list(self.question_results)
        return payload


def run_evaluation(
    project_root: Path | None = None,
    config: EvaluationConfig | None = None,
    embedding_provider_factory: EmbeddingProviderFactory | None = None,
    vector_store_wrapper: VectorStoreWrapper | None = None,
    search_service_factory: SearchServiceFactory | None = None,
    question_timing_observer: QuestionTimingObserver | None = None,
) -> EvaluationReport:
    root = project_root or Path(__file__).resolve().parents[1]
    active_config = config or EvaluationConfig()
    corpus_manifest = _load_json(root / "evaluation" / "corpus_sources.json")
    documents = corpus_manifest["documents"]
    questions = load_question_contracts(root / "evaluation" / "questions.json")
    corpus_summary = _validate_manifests(documents, questions, root)

    with tempfile.TemporaryDirectory() as temporary_directory:
        runtime_root = Path(temporary_directory)
        repository = SQLiteDocumentRepository(runtime_root / "app.db")
        repository.initialize()
        provider_factory = embedding_provider_factory or HashingEmbeddingProvider
        embedding_provider = provider_factory()
        llm_provider = EvaluationLLMProvider()
        profile = EvaluationProfile(
            name=active_config.name,
            corpus="tracked-synthetic-policy-corpus",
            embedding_provider=embedding_provider.name,
            embedding_model=getattr(embedding_provider, "model", None),
            embedding_dimensions=embedding_provider.dimensions,
            llm_provider=llm_provider.name,
            llm_model=llm_provider.model,
            chunk_size=active_config.chunk_size,
            chunk_overlap=active_config.chunk_overlap,
            top_k=active_config.top_k,
            answerable_score_threshold=None,
            unanswerable_score_threshold=active_config.unanswerable_score_threshold,
            ambiguity_score_margin=active_config.ambiguity_score_margin,
            minimum_evidence_hit_rate=MIN_EVIDENCE_HIT_RATE,
            minimum_evidence_recall=MIN_EVIDENCE_RECALL,
            minimum_evidence_mrr=MIN_EVIDENCE_MRR,
            minimum_unanswerable_rejection_rate=MIN_UNANSWERABLE_REJECTION_RATE,
        )
        base_vector_store = QdrantVectorStore(
            storage_path=runtime_root / "qdrant",
            collection_name="offline_evaluation_chunks",
            vector_size=embedding_provider.dimensions,
        )
        vector_store: VectorStore = (
            vector_store_wrapper(base_vector_store)
            if vector_store_wrapper is not None
            else base_vector_store
        )
        vector_store.initialize()
        try:
            ingestion_service = IngestionService(
                document_repository=repository,
                vector_store=vector_store,
                embedding_provider=embedding_provider,
                upload_dir=runtime_root / "uploads",
                max_upload_bytes=2 * 1024 * 1024,
                chunk_size=active_config.chunk_size,
                chunk_overlap=active_config.chunk_overlap,
            )
            document_service = DocumentService(
                document_repository=repository,
                vector_store=vector_store,
                upload_dir=runtime_root / "uploads",
            )

            ingested: dict[str, Document] = {}
            for document_spec in documents:
                source_path = (
                    root / "evaluation" / "documents" / document_spec["filename"]
                )
                with source_path.open("rb") as source:
                    ingested_document = ingestion_service.ingest(
                        source,
                        filename=document_spec["filename"],
                        media_type=document_spec["media_type"],
                    )
                ingested[document_spec["filename"]] = ingested_document

            retrieval_service = (
                search_service_factory(
                    repository,
                    vector_store,
                    embedding_provider,
                )
                if search_service_factory is not None
                else RetrievalService(
                    document_repository=repository,
                    vector_store=vector_store,
                    embedding_provider=embedding_provider,
                )
            )
            answer_service = AnswerService(retrieval_service, llm_provider)  # type: ignore[arg-type]

            metrics = _evaluate_questions(
                questions,
                ingested,
                retrieval_service,
                answer_service,
                top_k=active_config.top_k,
                unanswerable_score_threshold=(
                    active_config.unanswerable_score_threshold
                ),
                ambiguity_score_margin=active_config.ambiguity_score_margin,
                timing_observer=question_timing_observer,
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
                top_k=active_config.top_k,
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
        "question_count": corpus_summary["question_count"] == 50,
        "category_distribution": corpus_summary["category_counts"]
        == {
            "direct": 14,
            "multi_chunk": 6,
            "scope_isolation": 4,
            "unanswerable": 8,
            "paraphrase": 6,
            "distractor": 6,
            "low_score": 4,
            "ambiguous": 2,
        },
        "all_documents_ingested": len(ingested) == 10,
        "source_hit_rate_at_k": metrics["source_hit_rate_at_k"] >= 0.80,
        "evidence_hit_rate_at_k": metrics["evidence_hit_rate_at_k"]
        >= MIN_EVIDENCE_HIT_RATE,
        "evidence_recall_at_k": metrics["evidence_recall_at_k"] >= MIN_EVIDENCE_RECALL,
        "evidence_mean_reciprocal_rank": metrics["evidence_mean_reciprocal_rank"]
        >= MIN_EVIDENCE_MRR,
        "multi_chunk_pass_rate": metrics["multi_chunk_pass_rate"] == 1.0,
        "scope_isolation_pass_rate": metrics["scope_isolation_pass_rate"] == 1.0,
        "unanswerable_rejection_rate": metrics["unanswerable_rejection_rate"]
        >= MIN_UNANSWERABLE_REJECTION_RATE,
        "citation_integrity_pass_rate": metrics["citation_integrity_pass_rate"] == 1.0,
        "pdf_page_metadata_pass_rate": metrics["pdf_page_metadata_pass_rate"] == 1.0,
        "empty_chunk_invariant": empty_chunk_invariant,
        "deletion": deletion_passed,
    }
    failed_checks = tuple(name for name, passed in checks.items() if not passed)
    return EvaluationReport(
        passed=not failed_checks,
        profile=profile,
        document_count=corpus_summary["document_count"],
        txt_count=corpus_summary["txt_count"],
        pdf_count=corpus_summary["pdf_count"],
        multi_page_document_count=corpus_summary["multi_page_document_count"],
        question_count=corpus_summary["question_count"],
        category_counts=corpus_summary["category_counts"],
        category_metrics=metrics["category_metrics"],
        ingested_document_count=len(ingested),
        source_hit_rate_at_k=metrics["source_hit_rate_at_k"],
        evidence_hit_rate_at_k=metrics["evidence_hit_rate_at_k"],
        evidence_recall_at_k=metrics["evidence_recall_at_k"],
        evidence_mean_reciprocal_rank=metrics["evidence_mean_reciprocal_rank"],
        clarification_candidate_recall_at_k=metrics[
            "clarification_candidate_recall_at_k"
        ],
        clarification_response_rate=metrics["clarification_response_rate"],
        multi_chunk_pass_rate=metrics["multi_chunk_pass_rate"],
        scope_isolation_pass_rate=metrics["scope_isolation_pass_rate"],
        unanswerable_rejection_rate=metrics["unanswerable_rejection_rate"],
        citation_integrity_pass_rate=metrics["citation_integrity_pass_rate"],
        pdf_page_metadata_pass_rate=metrics["pdf_page_metadata_pass_rate"],
        empty_chunk_invariant_passed=empty_chunk_invariant,
        deletion_passed=deletion_passed,
        bad_case_count=sum(
            not question_result["passed"]
            for question_result in metrics["question_results"]
        ),
        failed_checks=failed_checks,
        question_results=metrics["question_results"],
    )


def _evaluate_questions(
    questions: list[EvaluationQuestion],
    ingested: dict[str, Document],
    retrieval_service: SearchService,
    answer_service: AnswerService,
    *,
    top_k: int,
    unanswerable_score_threshold: float,
    ambiguity_score_margin: float,
    timing_observer: QuestionTimingObserver | None,
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
        "clarification": 0,
        "clarification_pass": 0,
    }
    question_results: list[dict[str, Any]] = []
    answerable_rankings: list[list[RetrievalResult]] = []
    answerable_evidence: list[tuple[ExpectedEvidence, ...]] = []
    clarification_rankings: list[list[RetrievalResult]] = []
    clarification_evidence: list[tuple[ExpectedEvidence, ...]] = []

    for question in questions:
        scope_names = question.scope
        scope_ids = (
            all_document_ids
            if scope_names == ("*",)
            else [ingested[name].document_id for name in scope_names]
        )
        threshold = (
            unanswerable_score_threshold
            if question.expected_behavior == "refuse"
            else None
        )
        retrieval_started_at = perf_counter()
        results = retrieval_service.search(
            question.question,
            scope_ids,
            top_k=top_k,
            score_threshold=threshold,
        )
        retrieval_elapsed_ms = (perf_counter() - retrieval_started_at) * 1000
        answer_started_at = perf_counter()
        answer = answer_service.answer(
            question.question,
            scope_ids,
            top_k=top_k,
            score_threshold=threshold,
        )
        answer_elapsed_ms = (perf_counter() - answer_started_at) * 1000
        if timing_observer is not None:
            timing_observer(
                question,
                retrieval_elapsed_ms,
                answer_elapsed_ms,
            )
        retrieved_sources = {result.filename for result in results}
        expected_sources = set(question.expected_sources)
        source_pass = expected_sources.issubset(retrieved_sources)
        reasons: list[str] = []
        evidence_hit: float | None = None
        evidence_recall: float | None = None
        reciprocal_rank: float | None = None

        if question.expected_evidence:
            evidence_hit = hit_rate_at_k(
                [results],
                [question.expected_evidence],
                top_k,
                matcher=_result_contains_evidence,
            )
            evidence_recall = recall_at_k(
                [results],
                [question.expected_evidence],
                top_k,
                matcher=_result_contains_evidence,
            )
            reciprocal_rank = mean_reciprocal_rank(
                [results],
                [question.expected_evidence],
                matcher=_result_contains_evidence,
            )

        if question.answerable:
            answerable_rankings.append(results)
            answerable_evidence.append(question.expected_evidence)
            counters["answerable"] += 1
            counters["top5"] += int(source_pass)
            if not source_pass:
                reasons.append("expected_source_missing")
            if evidence_hit == 0.0:
                reasons.append("no_expected_evidence_in_top_k")
            elif evidence_recall < 1.0:
                reasons.append("incomplete_expected_evidence_in_top_k")

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

        if question.category == "multi_chunk":
            counters["multi"] += 1
            expected_chunk_count = question.minimum_expected_chunks
            assert expected_chunk_count is not None
            matching_chunks = sum(
                result.filename in expected_sources for result in results
            )
            multi_pass = matching_chunks >= expected_chunk_count
            counters["multi_pass"] += int(multi_pass)
            if not multi_pass:
                reasons.append("insufficient_expected_chunks")

        if question.category == "scope_isolation":
            counters["scope"] += 1
            scope_pass = all(result.filename in scope_names for result in results)
            counters["scope_pass"] += int(scope_pass)
            if not scope_pass:
                reasons.append("out_of_scope_result")

        if question.expected_behavior == "refuse":
            counters["unanswerable"] += 1
            unanswerable_pass = (
                not results
                and not answer.citations
                and answer.answer == NO_EVIDENCE_ANSWER
            )
            counters["unanswerable_pass"] += int(unanswerable_pass)
            if not unanswerable_pass:
                reasons.append("unsupported_answer")

        if question.expected_behavior == "clarify":
            counters["clarification"] += 1
            clarification_rankings.append(results)
            clarification_evidence.append(question.expected_evidence)
            reasons.append("clarification_not_supported")

        if expected_pages := question.expected_pages:
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
                "id": question.id,
                "category": question.category,
                "answerable": question.answerable,
                "expected_behavior": question.expected_behavior,
                "passed": not reasons,
                "score_threshold": threshold,
                "expected_answer": question.expected_answer,
                "expected_evidence": [
                    {
                        "evidence_number": evidence_number,
                        "filename": evidence.filename,
                        "page_number": evidence.page_number,
                        "snippet": evidence.snippet,
                    }
                    for evidence_number, evidence in enumerate(
                        question.expected_evidence,
                        start=1,
                    )
                ],
                "evidence_hit_at_k": evidence_hit,
                "evidence_recall_at_k": evidence_recall,
                "reciprocal_rank": reciprocal_rank,
                "top_score_gap": _top_score_gap(results),
                "near_top_candidate_count": _near_top_candidate_count(
                    results,
                    ambiguity_score_margin,
                ),
                "retrieved_sources": sorted(retrieved_sources),
                "result_count": len(results),
                "results": [
                    {
                        "rank": rank,
                        "filename": result.filename,
                        "page_number": result.page_number,
                        "score": round(result.score, 4),
                        "excerpt": " ".join(result.text.split())[:180],
                        "matched_evidence_numbers": [
                            evidence_number
                            for evidence_number, evidence in enumerate(
                                question.expected_evidence,
                                start=1,
                            )
                            if _result_contains_evidence(result, evidence)
                        ],
                    }
                    for rank, result in enumerate(results, start=1)
                ],
                "failures": reasons,
            }
        )

    aggregate_metrics = {
        "source_hit_rate_at_k": _rate(counters["top5"], counters["answerable"]),
        "evidence_hit_rate_at_k": round(
            hit_rate_at_k(
                answerable_rankings,
                answerable_evidence,
                top_k,
                matcher=_result_contains_evidence,
            ),
            4,
        ),
        "evidence_recall_at_k": round(
            recall_at_k(
                answerable_rankings,
                answerable_evidence,
                top_k,
                matcher=_result_contains_evidence,
            ),
            4,
        ),
        "evidence_mean_reciprocal_rank": round(
            mean_reciprocal_rank(
                answerable_rankings,
                answerable_evidence,
                matcher=_result_contains_evidence,
            ),
            4,
        ),
        "clarification_candidate_recall_at_k": round(
            recall_at_k(
                clarification_rankings,
                clarification_evidence,
                top_k,
                matcher=_result_contains_evidence,
            ),
            4,
        ),
        "clarification_response_rate": _rate(
            counters["clarification_pass"],
            counters["clarification"],
        ),
        "multi_chunk_pass_rate": _rate(counters["multi_pass"], counters["multi"]),
        "scope_isolation_pass_rate": _rate(counters["scope_pass"], counters["scope"]),
        "unanswerable_rejection_rate": _rate(
            counters["unanswerable_pass"], counters["unanswerable"]
        ),
        "citation_integrity_pass_rate": _rate(
            counters["citation_pass"], counters["citation"]
        ),
        "pdf_page_metadata_pass_rate": _rate(counters["pages_pass"], counters["pages"]),
        "question_results": tuple(question_results),
    }
    aggregate_metrics["category_metrics"] = _category_metrics(question_results)
    return aggregate_metrics


def _result_contains_evidence(
    result: RetrievalResult,
    evidence: ExpectedEvidence,
) -> bool:
    if result.filename != evidence.filename:
        return False
    if result.page_number != evidence.page_number:
        return False
    return _normalize_text(evidence.snippet) in _normalize_text(result.text)


def _normalize_text(value: str) -> str:
    return " ".join(value.split()).casefold()


def _top_score_gap(results: list[RetrievalResult]) -> float | None:
    if len(results) < 2:
        return None
    return round(results[0].score - results[1].score, 4)


def _near_top_candidate_count(
    results: list[RetrievalResult],
    score_margin: float,
) -> int:
    if not results:
        return 0
    top_score = results[0].score
    return sum(top_score - result.score <= score_margin for result in results)


def _category_metrics(
    question_results: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    metrics: dict[str, dict[str, Any]] = {}
    categories = dict.fromkeys(result["category"] for result in question_results)
    for category in categories:
        results = [
            result for result in question_results if result["category"] == category
        ]
        answerable_results = [result for result in results if result["answerable"]]
        evidence_results = [result for result in results if result["expected_evidence"]]
        metrics[category] = {
            "question_count": len(results),
            "answerable_count": len(answerable_results),
            "clarification_count": sum(
                result["expected_behavior"] == "clarify" for result in results
            ),
            "pass_rate": _rate(
                sum(result["passed"] for result in results),
                len(results),
            ),
            "evidence_hit_rate_at_k": _optional_mean(
                result["evidence_hit_at_k"] for result in evidence_results
            ),
            "evidence_recall_at_k": _optional_mean(
                result["evidence_recall_at_k"] for result in evidence_results
            ),
            "mean_reciprocal_rank": _optional_mean(
                result["reciprocal_rank"] for result in evidence_results
            ),
        }
    return metrics


def _evaluate_deletion(
    document_service: DocumentService,
    repository: SQLiteDocumentRepository,
    vector_store: VectorStore,
    embedding_provider: EmbeddingProvider,
    document: Document,
    *,
    top_k: int,
) -> bool:
    stored_path = document.stored_path
    document_service.delete_document(document.document_id)
    remaining = vector_store.search(
        embedding_provider.embed_query("privileged access recertification"),
        [document.document_id],
        limit=top_k,
    )
    return (
        repository.get(document.document_id) is None
        and not stored_path.exists()
        and not remaining
    )


def _validate_manifests(
    documents: list[dict[str, Any]],
    questions: list[EvaluationQuestion],
    root: Path,
) -> dict[str, Any]:
    filenames = [document["filename"] for document in documents]
    if len(filenames) != len(set(filenames)):
        raise ValueError("evaluation document filenames must be unique")
    question_ids = [question.id for question in questions]
    if len(question_ids) != len(set(question_ids)):
        raise ValueError("evaluation question IDs must be unique")

    documents_by_filename = {document["filename"]: document for document in documents}
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
        scope = question.scope
        if scope != ("*",) and not set(scope).issubset(known_filenames):
            raise ValueError(f"unknown scope document in {question.id}")
        if not set(question.expected_sources).issubset(known_filenames):
            raise ValueError(f"unknown expected source in {question.id}")
        if scope != ("*",) and not set(question.expected_sources).issubset(scope):
            raise ValueError(f"expected evidence is outside scope in {question.id}")

        for evidence in question.expected_evidence:
            document = documents_by_filename[evidence.filename]
            if document["media_type"] == "application/pdf":
                if evidence.page_number is None:
                    raise ValueError(f"PDF evidence needs a page in {question.id}")
                if evidence.page_number > len(document["pages"]):
                    raise ValueError(f"evidence page is out of range in {question.id}")
                source_text = document["pages"][evidence.page_number - 1]
            else:
                if evidence.page_number is not None:
                    raise ValueError(
                        f"TXT evidence cannot define a page in {question.id}"
                    )
                source_text = "\n".join(document["pages"])
            if evidence.snippet not in source_text:
                raise ValueError(f"evidence snippet is not exact in {question.id}")

    category_counts: dict[str, int] = {}
    for question in questions:
        category = question.category
        category_counts[category] = category_counts.get(category, 0) + 1

    return {
        "document_count": len(documents),
        "txt_count": sum(item["media_type"] == "text/plain" for item in documents),
        "pdf_count": sum(item["media_type"] == "application/pdf" for item in documents),
        "multi_page_document_count": sum(len(item["pages"]) > 1 for item in documents),
        "question_count": len(questions),
        "category_counts": category_counts,
    }


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _rate(passed: int, total: int) -> float:
    return round(passed / total, 4) if total else 0.0


def _optional_mean(values: Iterable[float | None]) -> float | None:
    present_values = [value for value in values if value is not None]
    if not present_values:
        return None
    return round(sum(present_values) / len(present_values), 4)
