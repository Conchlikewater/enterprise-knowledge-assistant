"""Run the pre-registered R4 synchronous/asynchronous ingestion benchmark."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.ingestion_benchmark import (  # noqa: E402
    IngestionBenchmarkConfig,
    run_ingestion_benchmark,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--qdrant-url",
        default=os.environ.get("RAG_TEST_QDRANT_URL", "http://127.0.0.1:6333"),
    )
    parser.add_argument("--quality-gate-evidence", required=True)
    parser.add_argument("--source-commit", default=_current_commit())
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evaluation/ingestion_benchmark_report.json"),
    )
    arguments = parser.parse_args()
    report = run_ingestion_benchmark(
        PROJECT_ROOT,
        IngestionBenchmarkConfig(
            qdrant_url=arguments.qdrant_url,
            quality_gate_evidence=arguments.quality_gate_evidence,
            source_commit=arguments.source_commit,
        ),
    )
    output_path = arguments.output
    if not output_path.is_absolute():
        output_path = PROJECT_ROOT / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report.to_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    payload = report.to_dict()
    print("ingestion_benchmark_completed=true")
    print(
        "sync_acceptance_ms="
        f"p50:{payload['synchronous']['single']['acceptance_ms']['p50_ms']:.4f},"
        f"p95:{payload['synchronous']['single']['acceptance_ms']['p95_ms']:.4f}"
    )
    print(
        "async_acceptance_ms="
        f"p50:{payload['asynchronous']['single']['acceptance_ms']['p50_ms']:.4f},"
        f"p95:{payload['asynchronous']['single']['acceptance_ms']['p95_ms']:.4f}"
    )
    print(
        "async_end_to_end_ms="
        f"p50:{payload['asynchronous']['single']['end_to_end_ms']['p50_ms']:.4f},"
        f"p95:{payload['asynchronous']['single']['end_to_end_ms']['p95_ms']:.4f}"
    )
    print(f"crash_recovery_passed={payload['crash_recovery']['passed']}")
    print(f"recommendation={payload['decision']['recommendation']}")
    print(f"report={output_path}")
    return 0


def _current_commit() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip() if completed.returncode == 0 else "unknown"


if __name__ == "__main__":
    raise SystemExit(main())
