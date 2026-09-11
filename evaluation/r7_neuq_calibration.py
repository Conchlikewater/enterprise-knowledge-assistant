"""Budget-gated, development-only calibration for the admitted NEUQ corpus.

Planning is offline.  A real call additionally requires a hash-bound approval
record; the formal 100-question file is never read by this module.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from openai import OpenAI

from app.providers.openai_embedding_provider import OpenAIEmbeddingProvider
from evaluation.r7_calibration import cosine, select_threshold
from evaluation.r7_chunk_profile_analysis import (
    PREFERRED_PROFILE,
    PROFILE_CANDIDATES,
    _admitted_inputs,
    _development_mapping,
)
from evaluation.r7_corpus_contract import build_complete_corpus

MODEL = "text-embedding-3-small"
DIMENSIONS = 1536
BATCH_SIZE = 64
PRICE_PER_MILLION_INPUT_TOKENS_USD = 0.02
MAX_REQUESTS = 21
MAX_INPUT_TOKEN_UPPER_BOUND = 2_000_000
MAX_BUDGET_USD = 0.04


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_hash(value) -> str:
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()


def prepare_inputs(r7_root: Path, candidate_path: Path):
    protocol_path = r7_root / "neuq_2023_protocol.json"
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    if protocol["status"] not in {
        "preregistered_except_semantic_threshold",
        "preregistered_frozen",
    }:
        raise ValueError("Unexpected preregistration status")
    assets = protocol["frozen_assets"]
    for asset in assets.values():
        if _file_hash(r7_root.parents[1] / asset["path"]) != asset["file_sha256"]:
            raise ValueError("Preregistration asset hash mismatch")

    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    admission = json.loads(
        (r7_root / "preparation/r7b_safe_corpus_admission_20260910.json").read_text(
            encoding="utf-8"
        )
    )
    development_path = r7_root / "neuq_2023_development_questions_draft.json"
    development = json.loads(development_path.read_text(encoding="utf-8"))
    blocks, sources, reviews, decisions = _admitted_inputs(candidate, admission)
    profile = PROFILE_CANDIDATES[PREFERRED_PROFILE]
    chunks = build_complete_corpus(blocks, sources, reviews, profile, decisions)
    mapping = _development_mapping(chunks, development)
    if mapping["mapped_targets"] != mapping["evidence_targets"]:
        raise ValueError("Development Gold does not survive selected chunking")
    gold_by_question: dict[str, set[str]] = {}
    for item in mapping["mappings"]:
        gold_by_question.setdefault(item["question_id"], set()).update(
            item["chunk_ids"]
        )
    texts = [chunk.text for chunk in chunks] + [
        item["question"] for item in development["questions"]
    ]
    # UTF-8 bytes are a conservative upper bound for byte-level BPE tokens and
    # avoid adding a tokenizer dependency solely for a budget check.
    token_upper_bound = sum(len(text.encode("utf-8")) for text in texts)
    requests = math.ceil(len(chunks) / BATCH_SIZE) + math.ceil(
        len(development["questions"]) / BATCH_SIZE
    )
    cost_upper_bound = (
        token_upper_bound * PRICE_PER_MILLION_INPUT_TOKENS_USD / 1_000_000
    )
    if (
        requests > MAX_REQUESTS
        or token_upper_bound > MAX_INPUT_TOKEN_UPPER_BOUND
        or cost_upper_bound > MAX_BUDGET_USD
    ):
        raise ValueError("Prepared calibration exceeds hard budget limits")
    plan = {
        "schema_version": "r7-neuq-development-calibration-plan-v1",
        "status": "awaiting_user_approval",
        "model": MODEL,
        "dimensions": DIMENSIONS,
        "batch_size": BATCH_SIZE,
        "document_count": admission["source_scope"]["documents"],
        "chunk_count": len(chunks),
        "development_question_count": len(development["questions"]),
        "requests_planned": requests,
        "sdk_retries": 0,
        "input_token_upper_bound": token_upper_bound,
        "estimated_cost_upper_bound_usd": cost_upper_bound,
        "hard_budget_usd": MAX_BUDGET_USD,
        "price_per_million_input_tokens_usd": (PRICE_PER_MILLION_INPUT_TOKENS_USD),
        "candidate_corpus_sha256": admission["output_sha256"]["candidate_corpus"],
        "chunk_profile_sha256": assets["chunk_profile"]["profile_sha256"],
        "development_questions_file_sha256": _file_hash(development_path),
        "formal_question_file_loaded": False,
        "formal_experiment_run": False,
        "external_provider_upload_currently_authorized": False,
    }
    return protocol, chunks, development["questions"], gold_by_question, plan


class MeteredClient:
    def __init__(self, client: Any, approval: dict) -> None:
        self.client = client
        self.embeddings = self
        self.approval = approval
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
            or self.attempt_count >= self.approval["max_requests"]
            or prospective > self.approval["max_input_token_upper_bound"]
            or prospective * PRICE_PER_MILLION_INPUT_TOKENS_USD / 1_000_000
            > self.approval["max_budget_usd"]
        ):
            raise ValueError("Embedding request exceeds the approved calibration scope")
        self.attempt_count += 1
        self.submitted_token_upper_bound = prospective
        started = time.perf_counter()
        receipt = {"request": self.attempt_count, "input_count": len(texts)}
        try:
            response = self.client.embeddings.create(**kwargs)
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
            response_model=response.model,
            prompt_tokens=response.usage.prompt_tokens,
            total_tokens=response.usage.total_tokens,
            latency_ms=round((time.perf_counter() - started) * 1000, 3),
        )
        self.receipts.append(receipt)
        return response


def _validate_approval(approval: dict, plan: dict) -> None:
    if (
        approval.get("status") != "approved_by_user"
        or approval.get("purpose") != "development_threshold_calibration_only"
        or approval.get("candidate_corpus_sha256") != plan["candidate_corpus_sha256"]
        or approval.get("model") != MODEL
        or approval.get("max_requests") != MAX_REQUESTS
        or approval.get("max_input_token_upper_bound") != MAX_INPUT_TOKEN_UPPER_BOUND
        or approval.get("max_budget_usd") != MAX_BUDGET_USD
        or approval.get("formal_100_question_run") is not False
    ):
        raise ValueError("Missing or mismatched user approval record")


def _rank(chunks, questions, gold_by_question, document_vectors, query_vectors):
    if len(chunks) != len(document_vectors) or len(questions) != len(query_vectors):
        raise ValueError("Embedding input/output count mismatch")
    rankings = []
    for question, query in zip(questions, query_vectors, strict=True):
        gold = gold_by_question.get(question["id"], set())
        candidates = [
            {
                "chunk_id": chunk.chunk_id,
                "source_id": chunk.source_id,
                "page_number": chunk.page_number,
                "score": cosine(query, vector),
                "matches_gold": chunk.chunk_id in gold,
            }
            for chunk, vector in zip(chunks, document_vectors, strict=True)
            if chunk.source_id in question["allowed_document_ids"]
        ]
        candidates.sort(key=lambda item: (-item["score"], item["chunk_id"]))
        rankings.append(
            {
                "question_id": question["id"],
                "answerable": question["answerable"],
                "top5": candidates[:5],
                "gold_chunk_ids": sorted(gold),
            }
        )
    return rankings


def run_calibration(
    r7_root: Path,
    candidate_path: Path,
    approval_path: Path,
    client: Any,
    output: Path,
    cache: Path,
) -> dict:
    if output.exists() or cache.exists():
        raise ValueError("Refusing to overwrite calibration artifacts")
    protocol, chunks, questions, gold, plan = prepare_inputs(r7_root, candidate_path)
    approval = json.loads(approval_path.read_text(encoding="utf-8"))
    _validate_approval(approval, plan)
    meter = MeteredClient(client, approval)
    provider = OpenAIEmbeddingProvider(
        api_key="injected-client",
        model=MODEL,
        dimensions=DIMENSIONS,
        batch_size=BATCH_SIZE,
        client=meter,
    )
    report = {
        "schema_version": "r7-neuq-development-calibration-v1",
        "started_at": datetime.now(UTC).isoformat(),
        "scope": "44-document admitted corpus and 10 development questions only",
        "plan": plan,
        "approval_sha256": _file_hash(approval_path),
        "formal_100_question_evaluation_run": False,
        "requests": meter.receipts,
    }
    try:
        document_vectors = provider.embed_documents([chunk.text for chunk in chunks])
        query_vectors = provider.embed_documents([q["question"] for q in questions])
        cache.write_text(
            json.dumps(
                {
                    "candidate_corpus_sha256": plan["candidate_corpus_sha256"],
                    "chunk_ids": [chunk.chunk_id for chunk in chunks],
                    "question_ids": [q["id"] for q in questions],
                    "document_vectors": document_vectors,
                    "query_vectors": query_vectors,
                },
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
        rankings = _rank(chunks, questions, gold, document_vectors, query_vectors)
        threshold_policy = {
            "threshold_candidate_min": protocol["retry_policy"]["candidate_range"][
                "minimum"
            ],
            "threshold_candidate_max": protocol["retry_policy"]["candidate_range"][
                "maximum"
            ],
            "threshold_candidate_step": protocol["retry_policy"]["candidate_range"][
                "step"
            ],
        }
        report.update(
            status="completed",
            selection=select_threshold(rankings, threshold_policy),
            rankings=rankings,
            vector_cache_sha256=_file_hash(cache),
        )
    except Exception as exc:
        report.update(status="failed", error_type=type(exc).__name__)
    report.update(
        completed_at=datetime.now(UTC).isoformat(),
        attempted_requests=meter.attempt_count,
        reported_total_tokens=sum(
            receipt.get("total_tokens", 0) for receipt in meter.receipts
        ),
        submitted_token_upper_bound=meter.submitted_token_upper_bound,
    )
    report["reported_cost_usd"] = (
        report["reported_total_tokens"] * PRICE_PER_MILLION_INPUT_TOKENS_USD / 1_000_000
    )
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--approval", type=Path)
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    r7_root = Path(__file__).resolve().parent / "r7"
    if not args.execute:
        plan = prepare_inputs(r7_root, args.candidate)[-1]
        args.output.write_text(json.dumps(plan, indent=2), encoding="utf-8")
        return
    if not args.approval or not args.cache:
        raise ValueError("Execution requires approval and cache paths")
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise ValueError("OPENAI_API_KEY is required")
    client = OpenAI(api_key=api_key, max_retries=0, timeout=30.0)
    try:
        run_calibration(
            r7_root,
            args.candidate,
            args.approval,
            client,
            args.output,
            args.cache,
        )
    finally:
        client.close()


if __name__ == "__main__":
    main()
