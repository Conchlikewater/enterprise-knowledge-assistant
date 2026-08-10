"""Run isolated offline retrieval experiments and compare their metrics."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.experiments import run_experiments  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print complete JSON.")
    parser.add_argument("--output", type=Path, help="Write JSON report to this path.")
    arguments = parser.parse_args()

    report = run_experiments(PROJECT_ROOT)
    serialized = json.dumps(report.to_dict(), indent=2, ensure_ascii=False)
    if arguments.output is not None:
        output_path = arguments.output
        if not output_path.is_absolute():
            output_path = PROJECT_ROOT / output_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(serialized + "\n", encoding="utf-8")

    if arguments.json:
        print(serialized)
    else:
        print(f"experiments_completed={str(report.all_runs_completed).lower()}")
        print(f"profiles={report.profile_count} questions={report.question_count}")
        for result in report.profiles:
            profile = result["profile"]
            print(
                f"profile={result['name']} "
                f"chunk={profile['chunk_size']}/{profile['chunk_overlap']} "
                f"top_k={profile['top_k']} "
                f"recall={result['evidence_recall_at_k']:.2%} "
                f"mrr={result['evidence_mean_reciprocal_rank']:.4f} "
                f"bad_cases={result['bad_case_count']}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
