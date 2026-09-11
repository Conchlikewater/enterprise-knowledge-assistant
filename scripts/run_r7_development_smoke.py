"""Run all three arms on development inputs; never load formal question labels."""

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import Settings  # noqa: E402
from app.providers.openai_embedding_provider import (  # noqa: E402
    OpenAIEmbeddingProvider,
)
from app.services.query_rewriter import RuleBasedQueryRewriter  # noqa: E402
from evaluation.experiments.r7_assets import load_local  # noqa: E402
from evaluation.experiments.r7_replay import pack_result, write_new  # noqa: E402
from evaluation.experiments.r7_retrieval import run_arm  # noqa: E402
from evaluation.r7_neuq_calibration import (  # noqa: E402
    DIMENSIONS,
    MODEL,
    MeteredClient,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--rewrite-cache", type=Path, required=True)
    parser.add_argument("--execute-approved", action="store_true")
    args = parser.parse_args()
    if args.output.exists() or args.rewrite_cache.exists():
        raise ValueError("Refusing to overwrite run artifacts")
    protocol, chunks, questions, dense, graph = load_local(
        ROOT, args.candidate, args.cache
    )
    # Fixed rewriter on development inputs only, before any result is observed.
    rewritten = sorted(
        {
            value
            for row in questions
            if (value := RuleBasedQueryRewriter().rewrite(row["question"]))
            and value not in dense.query_vectors
        }
    )
    upper = sum(len(text.encode("utf-8")) for text in rewritten)
    if len(rewritten) > 10 or upper > 10000:
        raise ValueError("Development rewrite plan exceeds budget")
    print(
        json.dumps(
            {
                "development_questions": len(questions),
                "rewrite_queries": len(rewritten),
                "requests_max": 1,
                "token_upper_bound": upper,
                "cost_upper_bound_usd": upper * 0.02 / 1_000_000,
            }
        )
    )
    if not args.execute_approved:
        return
    if protocol["authorization"].get("aggregate_budget_cny") != 10:
        raise ValueError("Budget authorization absent")
    report = {
        "scope": "development_only",
        "formal_questions_run": 0,
        "status": "running",
        "chunks": len(chunks),
        "graph_nodes": len(graph.nodes),
        "graph_edges": len(graph.edges),
        "provider_requests": [],
        "runs": [],
    }
    if rewritten:
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
                    "max_requests": 1,
                    "max_input_token_upper_bound": 10000,
                    "max_budget_usd": 0.0002,
                },
            )
            try:
                provider = OpenAIEmbeddingProvider(
                    api_key="injected", model=MODEL, dimensions=DIMENSIONS, client=meter
                )
                vectors = provider.embed_documents(rewritten)
            except Exception as exc:
                report.update(
                    status="provider_failed",
                    error_type=type(exc).__name__,
                    provider_requests=meter.receipts,
                )
                write_new(args.output, report)
                return 1
            report["provider_requests"] = meter.receipts
        additions = dict(zip(rewritten, vectors, strict=True))
        write_new(
            args.rewrite_cache,
            {"model": MODEL, "dimensions": DIMENSIONS, "query_vectors": additions},
        )
        dense.query_vectors.update(additions)
    try:
        for question in questions:
            for arm in protocol["retrieval_arms"]:
                result = run_arm(
                    question["question"],
                    question["allowed_document_ids"],
                    arm["id"],
                    dense,
                    graph,
                    protocol["retry_policy"]["semantic_score_threshold"],
                )
                report["runs"].append(pack_result(question["id"], arm["id"], result))
        report["status"] = "completed"
    except Exception as exc:
        report.update(status="retrieval_failed", error_type=type(exc).__name__)
    report["reported_tokens"] = sum(
        row.get("total_tokens", 0) for row in report["provider_requests"]
    )
    report["reported_cost_usd"] = report["reported_tokens"] * 0.02 / 1_000_000
    write_new(args.output, report)
    print(
        json.dumps(
            {
                key: report[key]
                for key in ("status", "reported_tokens", "reported_cost_usd")
            }
        )
    )
    print(f"development_arm_runs={len(report['runs'])}")
    return 0 if report["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
