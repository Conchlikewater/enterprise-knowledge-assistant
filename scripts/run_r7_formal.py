"""One frozen formal run; shared embeddings, deterministic arm rotation, no tuning."""

import argparse
import hashlib
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import Settings  # noqa: E402
from app.providers.openai_embedding_provider import (  # noqa: E402
    OpenAIEmbeddingProvider,
)
from app.services.query_rewriter import RuleBasedQueryRewriter  # noqa: E402
from evaluation.experiments.r7_assets import load_local, read_json, sha256  # noqa: E402
from evaluation.experiments.r7_replay import pack_result, write_new  # noqa: E402
from evaluation.experiments.r7_report import (  # noqa: E402
    ARMS,
    build_report,
    judge_promotion,
)
from evaluation.experiments.r7_retrieval import run_arm  # noqa: E402
from evaluation.r7_neuq_calibration import (  # noqa: E402
    DIMENSIONS,
    MODEL,
    MeteredClient,
)


def digest(value):
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()


def prepare(protocol, formal, gold):
    if not protocol["phase_gate"]["r7d_formal_results_allowed"]:
        raise ValueError("Formal gate is closed")
    expected = protocol["frozen_assets"]["gold"][
        "local_reconstructed_gold_canonical_sha256"
    ]
    if digest(gold) != expected:
        raise ValueError("Frozen Gold hash mismatch")
    # Retrieval inputs deliberately exclude labels, expected evidence and paths.
    questions = [
        {key: q[key] for key in ("id", "question", "allowed_document_ids")}
        for q in formal["questions"]
    ]
    ids = [q["id"] for q in questions]
    if (
        len(ids) != 100
        or len(set(ids)) != 100
        or set(ids) != {q["question_id"] for q in gold["questions"]}
    ):
        raise ValueError("Formal question identities differ")
    queries = {q["question"] for q in questions}
    queries.update(
        value
        for q in questions
        if (value := RuleBasedQueryRewriter().rewrite(q["question"]))
    )
    return questions, sorted(queries)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--execute-approved", action="store_true")
    args = parser.parse_args()
    if args.run_dir.exists():
        raise ValueError("Run directory already exists; refusing duplicate run")
    protocol, _, _, dense, graph = load_local(ROOT, args.candidate, args.cache)
    gold = read_json(args.gold)
    formal = read_json(ROOT / protocol["frozen_assets"]["formal_questions"]["path"])
    questions, queries = prepare(protocol, formal, gold)
    missing = [q for q in queries if q not in dense.query_vectors]
    upper = sum(len(q.encode("utf-8")) for q in missing)
    if len(missing) > 200 or upper > 100000:
        raise ValueError("Formal query budget exceeded")
    plan = {
        "questions": 100,
        "arms": 3,
        "query_vectors": len(missing),
        "requests_max": 4,
        "token_upper_bound": upper,
        "cost_upper_bound_usd": upper * 0.02 / 1000000,
        "hard_budget_usd": 0.002,
        "previous_cumulative_cost_usd": 0.00710462,
        "protocol_sha256": sha256(ROOT / "evaluation/r7/neuq_2023_protocol.json"),
        "gold_canonical_sha256": digest(gold),
        "formal_questions_sha256": digest(formal),
        "document_cache_sha256": sha256(args.cache),
        "code_sha256": {
            str(p.relative_to(ROOT)): sha256(p)
            for p in sorted((ROOT / "evaluation/experiments").glob("*.py"))
        },
        "runner_sha256": sha256(Path(__file__)),
        "arm_order": "rotate by sorted question index modulo three",
        "generation_llm_calls": 0,
    }
    print(
        json.dumps(
            {
                key: plan[key]
                for key in (
                    "query_vectors",
                    "requests_max",
                    "token_upper_bound",
                    "cost_upper_bound_usd",
                )
            }
        )
    )
    if not args.execute_approved:
        return 0
    if protocol["authorization"].get("aggregate_budget_cny") != 10:
        raise ValueError("User budget authorization absent")
    args.run_dir.mkdir(parents=True, exist_ok=False)
    write_new(args.run_dir / "pre_execution.json", plan)
    receipts = []
    records = []
    status = {"started_at": datetime.now(UTC).isoformat(), "status": "running"}
    try:
        if missing:
            from openai import OpenAI

            logging.getLogger("httpx").setLevel(logging.WARNING)
            settings = Settings.from_env(env_file=ROOT / ".env")
            with OpenAI(
                api_key=settings.openai_api_key,
                base_url="https://api.openai.com/v1",
                max_retries=0,
                timeout=30,
            ) as client:
                meter = MeteredClient(
                    client,
                    {
                        "max_requests": 4,
                        "max_input_token_upper_bound": 100000,
                        "max_budget_usd": 0.002,
                    },
                )
                receipts = meter.receipts
                provider = OpenAIEmbeddingProvider(
                    api_key="injected",
                    model=MODEL,
                    dimensions=DIMENSIONS,
                    batch_size=64,
                    client=meter,
                )
                vectors = provider.embed_documents(missing)
            additions = dict(zip(missing, vectors, strict=True))
            write_new(
                args.run_dir / "query_cache.json",
                {"model": MODEL, "query_vectors": additions},
            )
            dense.query_vectors.update(additions)
        for index, question in enumerate(sorted(questions, key=lambda q: q["id"])):
            order = ARMS[index % 3 :] + ARMS[: index % 3]
            for arm in order:
                result = run_arm(
                    question["question"],
                    question["allowed_document_ids"],
                    arm,
                    dense,
                    graph,
                    protocol["retry_policy"]["semantic_score_threshold"],
                )
                records.append(pack_result(question["id"], arm, result))
        write_new(args.run_dir / "trajectories.json", records)
        report = build_report(
            records,
            gold["questions"],
            {q["id"]: set(q["allowed_document_ids"]) for q in questions},
        )
        report["promotion"] = judge_promotion(report, protocol["promotion_gates"])
        write_new(args.run_dir / "report.json", report)
        status.update(status="completed", verdict=report["promotion"]["verdict"])
    except Exception as exc:
        status.update(status="failed", error_type=type(exc).__name__)
        if not (args.run_dir / "trajectories.json").exists():
            write_new(args.run_dir / "partial_trajectories.json", records)
    status.update(
        completed_at=datetime.now(UTC).isoformat(),
        completed_arm_runs=len(records),
        provider_requests=receipts,
        reported_tokens=sum(r.get("total_tokens", 0) for r in receipts),
    )
    status["reported_cost_usd"] = status["reported_tokens"] * 0.02 / 1000000
    write_new(args.run_dir / "status.json", status)
    print(
        json.dumps(
            {
                k: status[k]
                for k in (
                    "status",
                    "completed_arm_runs",
                    "reported_tokens",
                    "reported_cost_usd",
                )
            }
        )
    )
    return 0 if status["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
