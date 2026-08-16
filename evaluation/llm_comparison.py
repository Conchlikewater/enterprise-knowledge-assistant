"""Controlled generation-backend comparison over one shared retrieval run."""

from __future__ import annotations

import json
import re
import tempfile
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from html import escape
from pathlib import Path
from statistics import mean
from time import perf_counter
from typing import Any

from app.domain.models import Citation, Document, RetrievalResult
from app.providers.embedding_provider import EmbeddingProvider
from app.providers.llm_provider import (
    INSUFFICIENT_EVIDENCE_MARKER,
    LLMGenerationResult,
    LLMProvider,
    LLMTokenUsage,
)
from app.services.answer_service import NO_EVIDENCE_ANSWER
from app.services.ingestion_service import IngestionService
from app.services.retrieval_service import RetrievalService
from app.storage.qdrant_vector_store import QdrantVectorStore
from app.storage.sqlite_document_repository import SQLiteDocumentRepository
from evaluation.contracts import EvaluationQuestion, load_question_contracts

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
_CITATION_PATTERN = re.compile(r"\[([1-9][0-9]*)\]")


@dataclass(frozen=True, slots=True)
class ModelPrice:
    """USD price snapshot per one million tokens."""

    input_per_million: float
    cached_input_per_million: float
    output_per_million: float


@dataclass(frozen=True, slots=True)
class LLMComparisonConfig:
    chunk_size: int = 220
    chunk_overlap: int = 30
    top_k: int = 5
    score_threshold: float | None = None
    max_questions: int | None = None

    def __post_init__(self) -> None:
        if self.chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        if not 0 <= self.chunk_overlap < self.chunk_size:
            raise ValueError("chunk_overlap must be below chunk_size")
        if self.top_k <= 0:
            raise ValueError("top_k must be positive")
        if self.score_threshold is not None and not 0 <= self.score_threshold <= 1:
            raise ValueError("score_threshold must be between 0 and 1")
        if self.max_questions is not None and self.max_questions <= 0:
            raise ValueError("max_questions must be positive")


@dataclass(frozen=True, slots=True)
class LLMComparisonReport:
    corpus: str
    document_count: int
    question_count: int
    category_counts: dict[str, int]
    retrieval_profile: dict[str, Any]
    pricing_as_of: str
    provider_summaries: tuple[dict[str, Any], ...]
    question_results: tuple[dict[str, Any], ...]
    limitations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["provider_summaries"] = list(self.provider_summaries)
        payload["question_results"] = list(self.question_results)
        payload["limitations"] = list(self.limitations)
        return payload

    def to_markdown(self) -> str:
        lines = [
            "# OpenAI vs DeepSeek RAG Generation Comparison",
            "",
            f"Questions: {self.question_count}; documents: {self.document_count}; "
            f"pricing snapshot: {self.pricing_as_of}.",
            "",
            "| Metric | "
            + " | ".join(item["provider"] for item in self.provider_summaries)
            + " |",
            "|---|" + "---:|" * len(self.provider_summaries),
        ]
        metrics = (
            ("Model", "model", "{}"),
            ("Reference-answer token F1", "reference_answer_token_f1", "{:.2%}"),
            ("Answer/refusal behavior accuracy", "behavior_accuracy", "{:.2%}"),
            ("Citation marker validity", "citation_marker_validity", "{:.2%}"),
            (
                "Application citation integrity",
                "application_citation_integrity",
                "{:.2%}",
            ),
            ("Average LLM latency (ms)", "average_latency_ms", "{:.2f}"),
            ("P50 LLM latency (ms)", "p50_latency_ms", "{:.2f}"),
            ("P95 LLM latency (ms)", "p95_latency_ms", "{:.2f}"),
            ("Input tokens", "input_tokens", "{}"),
            ("Output tokens", "output_tokens", "{}"),
            ("Estimated API cost (USD)", "estimated_cost_usd", "{:.6f}"),
        )
        for label, key, template in metrics:
            values = []
            for summary in self.provider_summaries:
                value = summary[key]
                values.append(
                    "unavailable" if value is None else template.format(value)
                )
            lines.append(f"| {label} | " + " | ".join(values) + " |")
        lines.extend(("", "## Limitations", ""))
        lines.extend(f"- {item}" for item in self.limitations)
        return "\n".join(lines) + "\n"


def load_pricing_catalog(path: Path) -> tuple[str, dict[tuple[str, str], ModelPrice]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    as_of = payload["as_of"]
    models = {}
    for item in payload["models"]:
        models[(item["provider"], item["model"])] = ModelPrice(
            input_per_million=float(item["input_per_million"]),
            cached_input_per_million=float(item["cached_input_per_million"]),
            output_per_million=float(item["output_per_million"]),
        )
    return as_of, models


def run_llm_comparison(
    project_root: Path,
    embedding_provider: EmbeddingProvider,
    llm_providers: Sequence[LLMProvider],
    *,
    pricing_as_of: str,
    pricing: Mapping[tuple[str, str], ModelPrice],
    config: LLMComparisonConfig | None = None,
) -> LLMComparisonReport:
    active_config = config or LLMComparisonConfig()
    if len(llm_providers) < 2:
        raise ValueError("at least two LLM providers are required for comparison")
    identities = [(provider.name, provider.model) for provider in llm_providers]
    if len(identities) != len(set(identities)):
        raise ValueError("LLM provider/model identities must be unique")

    questions = load_question_contracts(project_root / "evaluation" / "questions.json")
    if active_config.max_questions is not None:
        questions = questions[: active_config.max_questions]
    corpus = json.loads(
        (project_root / "evaluation" / "corpus_sources.json").read_text(
            encoding="utf-8"
        )
    )["documents"]
    accumulators = {identity: _ProviderAccumulator() for identity in identities}

    try:
        with tempfile.TemporaryDirectory() as temporary_directory:
            runtime_root = Path(temporary_directory)
            repository = SQLiteDocumentRepository(runtime_root / "app.db")
            repository.initialize()
            vector_store = QdrantVectorStore(
                storage_path=runtime_root / "qdrant",
                collection_name="llm_comparison_chunks",
                vector_size=embedding_provider.dimensions,
            )
            vector_store.initialize()
            try:
                ingestion = IngestionService(
                    document_repository=repository,
                    vector_store=vector_store,
                    embedding_provider=embedding_provider,
                    upload_dir=runtime_root / "uploads",
                    max_upload_bytes=2 * 1024 * 1024,
                    chunk_size=active_config.chunk_size,
                    chunk_overlap=active_config.chunk_overlap,
                )
                ingested = _ingest_corpus(project_root, corpus, ingestion)
                retrieval = RetrievalService(
                    document_repository=repository,
                    vector_store=vector_store,
                    embedding_provider=embedding_provider,
                )
                question_results = tuple(
                    _evaluate_question(
                        question,
                        ingested,
                        retrieval,
                        llm_providers,
                        accumulators,
                        active_config,
                    )
                    for question in questions
                )
            finally:
                vector_store.close()
    finally:
        try:
            for provider in llm_providers:
                provider.close()
        finally:
            embedding_provider.close()

    summaries = tuple(
        accumulators[(provider.name, provider.model)].summarize(
            provider.name,
            provider.model,
            pricing.get((provider.name, provider.model)),
        )
        for provider in llm_providers
    )
    category_counts = Counter(question.category for question in questions)
    return LLMComparisonReport(
        corpus="tracked-synthetic-policy-corpus",
        document_count=len(corpus),
        question_count=len(questions),
        category_counts=dict(category_counts),
        retrieval_profile={
            "embedding_provider": embedding_provider.name,
            "embedding_model": getattr(embedding_provider, "model", None),
            "embedding_dimensions": embedding_provider.dimensions,
            "chunk_size": active_config.chunk_size,
            "chunk_overlap": active_config.chunk_overlap,
            "top_k": active_config.top_k,
            "score_threshold": active_config.score_threshold,
        },
        pricing_as_of=pricing_as_of,
        provider_summaries=summaries,
        question_results=question_results,
        limitations=(
            "The corpus and questions are synthetic and do not establish production accuracy.",
            "Reference-answer token F1 is a deterministic proxy and may penalize valid paraphrases.",
            "Only answer/refuse behavior is scored; the current production prompt has no clarification response.",
            "Application citations are constructed from retrieved chunks; citation-marker validity separately checks the model text.",
            "Latency measures sequential provider calls on this machine and is not a concurrency benchmark.",
        ),
    )


class _ProviderAccumulator:
    def __init__(self) -> None:
        self.quality_scores: list[float] = []
        self.behavior_scores: list[bool] = []
        self.citation_marker_scores: list[bool] = []
        self.application_citation_scores: list[bool] = []
        self.latencies_ms: list[float] = []
        self.usages: list[LLMTokenUsage] = []
        self.model_call_count = 0

    def add(
        self,
        *,
        quality_score: float | None,
        behavior_correct: bool | None,
        citation_markers_valid: bool | None,
        application_citations_valid: bool | None,
        latency_ms: float | None,
        usage: LLMTokenUsage | None,
        model_called: bool,
    ) -> None:
        if quality_score is not None:
            self.quality_scores.append(quality_score)
        if behavior_correct is not None:
            self.behavior_scores.append(behavior_correct)
        if citation_markers_valid is not None:
            self.citation_marker_scores.append(citation_markers_valid)
        if application_citations_valid is not None:
            self.application_citation_scores.append(application_citations_valid)
        if latency_ms is not None:
            self.latencies_ms.append(latency_ms)
        if usage is not None:
            self.usages.append(usage)
        self.model_call_count += int(model_called)

    def summarize(
        self,
        provider: str,
        model: str,
        price: ModelPrice | None,
    ) -> dict[str, Any]:
        input_tokens = sum(item.input_tokens for item in self.usages)
        cached_input_tokens = sum(item.cached_input_tokens for item in self.usages)
        output_tokens = sum(item.output_tokens for item in self.usages)
        reasoning_tokens = sum(item.reasoning_tokens for item in self.usages)
        usage_complete = len(self.usages) == self.model_call_count
        estimated_cost = (
            _estimate_cost(
                input_tokens,
                cached_input_tokens,
                output_tokens,
                price,
            )
            if usage_complete and price is not None
            else None
        )
        return {
            "provider": provider,
            "model": model,
            "model_call_count": self.model_call_count,
            "quality_scored_question_count": len(self.quality_scores),
            "behavior_scored_question_count": len(self.behavior_scores),
            "reference_answer_token_f1": _optional_mean(self.quality_scores),
            "behavior_accuracy": _optional_rate(self.behavior_scores),
            "citation_marker_validity": _optional_rate(self.citation_marker_scores),
            "application_citation_integrity": _optional_rate(
                self.application_citation_scores
            ),
            "average_latency_ms": _optional_mean(self.latencies_ms),
            "p50_latency_ms": _percentile(self.latencies_ms, 0.50),
            "p95_latency_ms": _percentile(self.latencies_ms, 0.95),
            "token_usage_complete": usage_complete,
            "input_tokens": input_tokens if usage_complete else None,
            "cached_input_tokens": (cached_input_tokens if usage_complete else None),
            "output_tokens": output_tokens if usage_complete else None,
            "reasoning_tokens": reasoning_tokens if usage_complete else None,
            "estimated_cost_usd": estimated_cost,
        }


def _ingest_corpus(
    project_root: Path,
    corpus: Sequence[dict[str, Any]],
    ingestion: IngestionService,
) -> dict[str, Document]:
    ingested = {}
    for item in corpus:
        path = project_root / "evaluation" / "documents" / item["filename"]
        with path.open("rb") as source:
            document = ingestion.ingest(
                source,
                filename=item["filename"],
                media_type=item["media_type"],
            )
        ingested[item["filename"]] = document
    return ingested


def _evaluate_question(
    question: EvaluationQuestion,
    ingested: Mapping[str, Document],
    retrieval: RetrievalService,
    providers: Sequence[LLMProvider],
    accumulators: Mapping[tuple[str, str], _ProviderAccumulator],
    config: LLMComparisonConfig,
) -> dict[str, Any]:
    scope_ids = (
        [document.document_id for document in ingested.values()]
        if question.scope == ("*",)
        else [ingested[name].document_id for name in question.scope]
    )
    retrieval_started = perf_counter()
    results = retrieval.search(
        question.question,
        scope_ids,
        top_k=config.top_k,
        score_threshold=config.score_threshold,
    )
    retrieval_latency_ms = (perf_counter() - retrieval_started) * 1000
    evidence_complete = _evidence_complete(question, results)
    provider_results = []
    for provider in providers:
        outcome = _generate_for_provider(question, results, provider, evidence_complete)
        accumulators[(provider.name, provider.model)].add(**outcome["metrics"])
        provider_results.append(outcome["result"])
    return {
        "question_id": question.id,
        "category": question.category,
        "expected_behavior": question.expected_behavior,
        "retrieval_count": len(results),
        "retrieval_latency_ms": retrieval_latency_ms,
        "expected_evidence_complete": evidence_complete,
        "providers": provider_results,
    }


def _generate_for_provider(
    question: EvaluationQuestion,
    results: Sequence[RetrievalResult],
    provider: LLMProvider,
    evidence_complete: bool,
) -> dict[str, Any]:
    generation: LLMGenerationResult | None = None
    latency_ms: float | None = None
    if results:
        started = perf_counter()
        generation = provider.generate_answer(
            question.question,
            _context_blocks(results),
        )
        latency_ms = (perf_counter() - started) * 1000
        refused = _is_refusal(generation.text)
        answer = NO_EVIDENCE_ANSWER if refused else generation.text.strip()
    else:
        refused = True
        answer = NO_EVIDENCE_ANSWER

    behavior_correct = _behavior_correct(question.expected_behavior, refused)
    quality_score = (
        _token_f1(answer, question.expected_answer)
        if question.expected_answer is not None and evidence_complete and not refused
        else None
    )
    citation_markers_valid = (
        _citation_markers_valid(answer, len(results)) if not refused else None
    )
    application_citations_valid = (
        _application_citations_valid(results) if not refused else None
    )
    usage = generation.usage if generation is not None else None
    return {
        "result": {
            "provider": provider.name,
            "model": provider.model,
            "model_called": generation is not None,
            "answer": answer,
            "refused": refused,
            "behavior_correct": behavior_correct,
            "reference_answer_token_f1": quality_score,
            "citation_markers_valid": citation_markers_valid,
            "application_citations_valid": application_citations_valid,
            "latency_ms": latency_ms,
            "usage": asdict(usage) if usage is not None else None,
        },
        "metrics": {
            "quality_score": quality_score,
            "behavior_correct": behavior_correct,
            "citation_markers_valid": citation_markers_valid,
            "application_citations_valid": application_citations_valid,
            "latency_ms": latency_ms,
            "usage": usage,
            "model_called": generation is not None,
        },
    }


def _context_blocks(results: Sequence[RetrievalResult]) -> list[str]:
    return [
        f'<source id="{index}">\n{escape(result.text, quote=False)}\n</source>'
        for index, result in enumerate(results, start=1)
    ]


def _evidence_complete(
    question: EvaluationQuestion,
    results: Sequence[RetrievalResult],
) -> bool:
    return all(
        any(
            result.filename == evidence.filename
            and result.page_number == evidence.page_number
            and _normalize(evidence.snippet) in _normalize(result.text)
            for result in results
        )
        for evidence in question.expected_evidence
    )


def _behavior_correct(expected_behavior: str, refused: bool) -> bool | None:
    if expected_behavior == "answer":
        return not refused
    if expected_behavior == "refuse":
        return refused
    return None


def _is_refusal(answer: str) -> bool:
    return answer.strip().rstrip(".").upper() == INSUFFICIENT_EVIDENCE_MARKER


def _citation_markers_valid(answer: str, result_count: int) -> bool:
    markers = {int(value) for value in _CITATION_PATTERN.findall(answer)}
    return bool(markers) and all(1 <= marker <= result_count for marker in markers)


def _application_citations_valid(results: Sequence[RetrievalResult]) -> bool:
    citations = tuple(
        Citation.from_result(result, citation_number=index)
        for index, result in enumerate(results, start=1)
    )
    return len(citations) == len(results) and all(
        citation.chunk_id == result.chunk_id
        and citation.document_id == result.document_id
        and citation.filename == result.filename
        and citation.page_number == result.page_number
        for citation, result in zip(citations, results, strict=True)
    )


def _token_f1(answer: str, reference: str) -> float:
    answer_without_citations = _CITATION_PATTERN.sub("", answer)
    answer_tokens = Counter(_TOKEN_PATTERN.findall(answer_without_citations.lower()))
    reference_tokens = Counter(_TOKEN_PATTERN.findall(reference.lower()))
    overlap = sum((answer_tokens & reference_tokens).values())
    if not answer_tokens or not reference_tokens or overlap == 0:
        return 0.0
    precision = overlap / sum(answer_tokens.values())
    recall = overlap / sum(reference_tokens.values())
    return 2 * precision * recall / (precision + recall)


def _estimate_cost(
    input_tokens: int,
    cached_input_tokens: int,
    output_tokens: int,
    price: ModelPrice,
) -> float:
    uncached_input_tokens = input_tokens - cached_input_tokens
    return (
        uncached_input_tokens * price.input_per_million
        + cached_input_tokens * price.cached_input_per_million
        + output_tokens * price.output_per_million
    ) / 1_000_000


def _percentile(values: Sequence[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = (len(ordered) - 1) * percentile
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = index - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _optional_mean(values: Sequence[float]) -> float | None:
    return mean(values) if values else None


def _optional_rate(values: Sequence[bool]) -> float | None:
    return sum(values) / len(values) if values else None


def _normalize(value: str) -> str:
    return " ".join(value.lower().split())
