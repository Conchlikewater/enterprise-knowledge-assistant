"""Budgeted, development-only calibration; never load the final question set."""

from __future__ import annotations

import hashlib
import json
import math
import time
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from app.document_processing.chunker import chunk_sections
from app.document_processing.loaders import load_pdf
from app.providers.openai_embedding_provider import OpenAIEmbeddingProvider

MODEL = "text-embedding-3-small"
DIMENSIONS = 1536
PRICE_PER_MILLION = 0.02
MAX_REQUESTS = 3
MAX_INPUT_TOKEN_UPPER_BOUND = 20_000
MAX_BUDGET_USD = 0.01


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _normalize(text: str) -> str:
    return " ".join(text.split())


def prepare_inputs(root: Path) -> tuple[dict, list, list[dict], dict]:
    protocol = json.loads((root / "protocol.json").read_text(encoding="utf-8"))
    assets = protocol["frozen_assets"]
    for name, key in (
        ("corpus_sources.json", "source_manifest_sha256"),
        ("corpus_manifest.json", "fixture_manifest_sha256"),
        ("development_questions.json", "development_set_sha256"),
    ):
        if _hash(root / name) != assets[key]:
            raise ValueError(f"Calibration input hash mismatch: {name}")
    manifest = json.loads((root / "corpus_manifest.json").read_text(encoding="utf-8"))
    questions = json.loads(
        (root / "development_questions.json").read_text(encoding="utf-8")
    )["questions"]
    chunks = []
    for document in manifest["documents"]:
        path = root / "documents" / document["filename"]
        if path.name != document["filename"] or _hash(path) != document["sha256"]:
            raise ValueError("Calibration PDF hash mismatch")
        document_id = uuid5(NAMESPACE_URL, f"r7:{document['source_id']}")
        parsed = chunk_sections(
            load_pdf(path),
            document_id,
            path.name,
            protocol["chunking"]["chunk_size"],
            protocol["chunking"]["chunk_overlap"],
        )
        chunks.extend(
            replace(
                chunk,
                chunk_id=uuid5(
                    document_id,
                    f"{chunk.page_number}:{chunk.chunk_index}:{chunk.content_hash}",
                ),
            )
            for chunk in parsed
        )
    for question in questions:
        if question["answerable"] and not any(
            evidence_matches(chunk, question["expected_evidence"]) for chunk in chunks
        ):
            raise ValueError(f"No matching development evidence: {question['id']}")
    texts = [c.text for c in chunks] + [q["question"] for q in questions]
    # UTF-8 bytes upper-bound byte-level BPE tokens, avoiding a new tokenizer
    # dependency. This is deliberately conservative, not an actual token count.
    upper_bound = sum(len(text.encode("utf-8")) for text in texts)
    requests = math.ceil(len(chunks) / 64) + math.ceil(len(questions) / 64)
    if upper_bound > MAX_INPUT_TOKEN_UPPER_BOUND or requests > MAX_REQUESTS:
        raise ValueError("Prepared inputs exceed the authorized calibration limits")
    plan = {
        "model": MODEL,
        "dimensions": DIMENSIONS,
        "document_count": len(manifest["documents"]),
        "chunk_count": len(chunks),
        "development_question_count": len(questions),
        "requests_planned": requests,
        "sdk_retries": 0,
        "input_token_upper_bound": upper_bound,
        "estimated_cost_upper_bound_usd": upper_bound * PRICE_PER_MILLION / 1e6,
        "approved_budget_usd": MAX_BUDGET_USD,
        "price_per_million_input_tokens_usd": PRICE_PER_MILLION,
        "source_manifest_sha256": assets["source_manifest_sha256"],
        "fixture_manifest_sha256": assets["fixture_manifest_sha256"],
        "development_set_sha256": assets["development_set_sha256"],
        "chunking": protocol["chunking"],
        "final_question_set_loaded": False,
    }
    return protocol, chunks, questions, plan


def evidence_matches(chunk: Any, evidence: list[dict]) -> bool:
    return any(
        chunk.filename == item["filename"]
        and chunk.page_number == item["page_number"]
        and _normalize(item["snippet"]) in _normalize(chunk.text)
        for item in evidence
    )


class MeteredClient:
    """Expose only the embedding call needed by the existing adapter."""

    def __init__(self, client: Any) -> None:
        self.client = client
        self.embeddings = self
        self.receipts: list[dict] = []
        self.attempt_count = 0
        self.submitted_token_upper_bound = 0

    def create(self, **kwargs: Any) -> Any:
        texts = kwargs["input"]
        upper_bound = sum(len(text.encode("utf-8")) for text in texts)
        prospective = self.submitted_token_upper_bound + upper_bound
        if (
            kwargs.get("model") != MODEL
            or kwargs.get("dimensions") != DIMENSIONS
            or self.attempt_count >= MAX_REQUESTS
            or prospective > MAX_INPUT_TOKEN_UPPER_BOUND
            or prospective * PRICE_PER_MILLION / 1e6 > MAX_BUDGET_USD
        ):
            raise ValueError("Embedding request exceeds approved limits")
        self.attempt_count += 1
        self.submitted_token_upper_bound = prospective
        started = time.perf_counter()
        receipt = {"request": self.attempt_count, "input_count": len(texts)}
        try:
            result = self.client.embeddings.create(**kwargs)
        except Exception as exc:
            receipt.update(
                status="failed",
                error_type=type(exc).__name__,
                latency_ms=round((time.perf_counter() - started) * 1000, 3),
            )
            self.receipts.append(receipt)
            raise
        receipt.update(
            status="completed",
            response_model=result.model,
            prompt_tokens=result.usage.prompt_tokens,
            total_tokens=result.usage.total_tokens,
            latency_ms=round((time.perf_counter() - started) * 1000, 3),
        )
        self.receipts.append(receipt)
        return result


def cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        raise ValueError("Embedding dimensions mismatch")
    norm = math.sqrt(sum(x * x for x in left) * sum(x * x for x in right))
    if norm == 0 or not math.isfinite(norm):
        raise ValueError("Embedding has invalid norm")
    return sum(x * y for x, y in zip(left, right, strict=True)) / norm


def rank_development(chunks, questions, document_vectors, query_vectors) -> list[dict]:
    rankings = []
    if len(document_vectors) != len(chunks) or len(query_vectors) != len(questions):
        raise ValueError("Embedding input/output count mismatch")
    for question, query in zip(questions, query_vectors, strict=True):
        candidates = [
            {
                "chunk_id": str(chunk.chunk_id),
                "document_id": str(chunk.document_id),
                "filename": chunk.filename,
                "page_number": chunk.page_number,
                "score": cosine(query, vector),
                "matches_gold": evidence_matches(chunk, question["expected_evidence"]),
            }
            for chunk, vector in zip(chunks, document_vectors, strict=True)
        ]
        candidates.sort(key=lambda item: (-item["score"], item["chunk_id"]))
        rankings.append(
            {
                "question_id": question["id"],
                "answerable": question["answerable"],
                "top5": candidates[:5],
            }
        )
    return rankings


def select_threshold(rankings: list[dict], retry_policy: dict) -> dict:
    """Execute the previously registered rule, including no eligible candidate."""
    minimum = retry_policy["threshold_candidate_min"]
    maximum = retry_policy["threshold_candidate_max"]
    step = retry_policy["threshold_candidate_step"]
    answerable_count = sum(row["answerable"] for row in rankings)
    if not answerable_count or not any(not row["answerable"] for row in rankings):
        raise ValueError("Calibration requires answerable and unsupported examples")
    rows = []
    for index in range(round((maximum - minimum) / step) + 1):
        threshold = round(minimum + index * step, 8)
        retained_gold = 0
        unsupported_with_fewer_than_two = 0
        reciprocal_ranks = []
        for row in rankings:
            kept = [item for item in row["top5"] if item["score"] >= threshold]
            if row["answerable"]:
                first = next(
                    (i for i, item in enumerate(kept, 1) if item["matches_gold"]),
                    None,
                )
                retained_gold += first is not None
                reciprocal_ranks.append(0.0 if first is None else 1.0 / first)
            else:
                unsupported_with_fewer_than_two += len(kept) < 2
        rows.append(
            {
                "threshold": threshold,
                "eligible": retained_gold == answerable_count,
                "answerable_questions_retaining_gold": retained_gold,
                "unsupported_with_fewer_than_two": unsupported_with_fewer_than_two,
                "answerable_mrr": sum(reciprocal_ranks) / answerable_count,
            }
        )
    eligible = [row for row in rows if row["eligible"]]
    best = max(
        eligible,
        key=lambda row: (
            row["unsupported_with_fewer_than_two"],
            row["answerable_mrr"],
            -row["threshold"],
        ),
        default=None,
    )
    return {
        "status": "selected" if best else "no_eligible_threshold",
        "selected_threshold": None if best is None else best["threshold"],
        "selected_row": best,
        "candidate_scan": rows,
    }


def write_new_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2, default=str)
        stream.write("\n")


def run_calibration(root: Path, client: Any, output: Path, cache: Path) -> dict:
    if output.exists() or cache.exists():
        raise ValueError("Refusing to overwrite an existing calibration run")
    protocol, chunks, questions, plan = prepare_inputs(root)
    meter = MeteredClient(client)
    provider = OpenAIEmbeddingProvider(
        api_key="injected-client", model=MODEL, dimensions=DIMENSIONS, client=meter
    )
    report = {
        "schema_version": "r7-development-calibration-v1",
        "started_at": datetime.now(UTC).isoformat(),
        "plan": plan,
        "scope": "Existing 12-document corpus and 10 development questions only",
        "corpus_expansion_requires_revalidation": True,
        "formal_100_question_evaluation_run": False,
        "requests": meter.receipts,
    }
    try:
        document_vectors = provider.embed_documents([chunk.text for chunk in chunks])
        query_vectors = provider.embed_documents([q["question"] for q in questions])
        write_new_json(
            cache,
            {
                "plan": plan,
                "chunks": [asdict(chunk) for chunk in chunks],
                "question_ids": [q["id"] for q in questions],
                "document_vectors": document_vectors,
                "query_vectors": query_vectors,
            },
        )
        rankings = rank_development(chunks, questions, document_vectors, query_vectors)
        report.update(
            status="completed",
            selection=select_threshold(rankings, protocol["retry_policy"]),
            rankings=rankings,
            vector_cache_sha256=_hash(cache),
        )
    except Exception as exc:
        report.update(status="failed", error_type=type(exc).__name__)
    report["completed_at"] = datetime.now(UTC).isoformat()
    report["attempted_requests"] = meter.attempt_count
    report["reported_total_tokens"] = sum(
        receipt.get("total_tokens", 0) for receipt in meter.receipts
    )
    report["reported_cost_usd"] = (
        report["reported_total_tokens"] * PRICE_PER_MILLION / 1e6
    )
    report["submitted_token_upper_bound"] = meter.submitted_token_upper_bound
    report["submitted_cost_upper_bound_usd"] = (
        meter.submitted_token_upper_bound * PRICE_PER_MILLION / 1e6
    )
    write_new_json(output, report)
    return report
