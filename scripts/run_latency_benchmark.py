"""Measure local retrieval and answer-pipeline P50/P95 latency."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.latency import run_latency_benchmark  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evaluation/latency_report.json"),
    )
    arguments = parser.parse_args()
    report = run_latency_benchmark(
        PROJECT_ROOT,
        rounds=arguments.rounds,
        warmup_questions_per_round=arguments.warmup,
    )
    output_path = arguments.output
    if not output_path.is_absolute():
        output_path = PROJECT_ROOT / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report.to_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print("latency_benchmark_completed=true")
    print(f"samples={report.measured_samples}")
    print(
        "retrieval_ms="
        f"p50:{report.retrieval_only_ms['p50']:.4f},"
        f"p95:{report.retrieval_only_ms['p95']:.4f}"
    )
    print(
        "answer_pipeline_ms="
        f"p50:{report.answer_pipeline_ms['p50']:.4f},"
        f"p95:{report.answer_pipeline_ms['p95']:.4f}"
    )
    print(f"report={output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
