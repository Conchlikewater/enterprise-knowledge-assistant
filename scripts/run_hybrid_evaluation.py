"""Run the offline dense-versus-hybrid retrieval experiment."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.hybrid_experiment import run_hybrid_comparison  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evaluation/hybrid_report.json"),
        help="Write the complete JSON report to this path.",
    )
    arguments = parser.parse_args()
    report = run_hybrid_comparison(PROJECT_ROOT)
    output_path = arguments.output
    if not output_path.is_absolute():
        output_path = PROJECT_ROOT / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report.to_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print("comparison_completed=true")
    print(f"questions={report.question_count}")
    print(
        "dense="
        f"recall:{report.dense['evidence_recall_at_k']:.2%},"
        f"mrr:{report.dense['evidence_mean_reciprocal_rank']:.4f},"
        f"retrieval_bad_cases:{report.dense['retrieval_bad_case_count']}"
    )
    print(
        "hybrid="
        f"recall:{report.hybrid['evidence_recall_at_k']:.2%},"
        f"mrr:{report.hybrid['evidence_mean_reciprocal_rank']:.4f},"
        f"retrieval_bad_cases:{report.hybrid['retrieval_bad_case_count']}"
    )
    print(f"delta_vs_dense={report.delta_vs_dense}")
    print(
        "candidate_threshold="
        f"{report.threshold_analysis['recommended_threshold_on_this_dataset']}"
    )
    print(
        "production_change_recommended="
        f"{str(report.production_change_recommended).lower()}"
    )
    print(f"decision_reasons={','.join(report.decision_reasons)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
