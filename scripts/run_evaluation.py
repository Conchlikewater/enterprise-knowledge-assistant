"""Run the offline portfolio evaluation and exit non-zero when a gate fails."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.runner import run_evaluation  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the complete machine-readable report.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Write the complete JSON report to this path.",
    )
    arguments = parser.parse_args()
    report = run_evaluation(PROJECT_ROOT)
    serialized_report = json.dumps(report.to_dict(), indent=2, ensure_ascii=False)

    if arguments.output is not None:
        output_path = arguments.output
        if not output_path.is_absolute():
            output_path = PROJECT_ROOT / output_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(serialized_report + "\n", encoding="utf-8")

    if arguments.json:
        print(serialized_report)
    else:
        print(f"evaluation_passed={str(report.passed).lower()}")
        print(
            "corpus="
            f"{report.document_count} documents "
            f"({report.txt_count} TXT, {report.pdf_count} PDF, "
            f"{report.multi_page_document_count} multi-page)"
        )
        print(f"questions={report.question_count} {report.category_counts}")
        print(
            "profile="
            f"embedding:{report.profile.embedding_provider}/"
            f"{report.profile.embedding_dimensions},"
            f"chunk:{report.profile.chunk_size}/"
            f"{report.profile.chunk_overlap},"
            f"top_k:{report.profile.top_k}"
        )
        print(
            f"source_hit_rate_at_{report.profile.top_k}="
            f"{report.source_hit_rate_at_k:.2%}"
        )
        print(
            f"evidence_hit_rate_at_{report.profile.top_k}="
            f"{report.evidence_hit_rate_at_k:.2%}"
        )
        print(
            f"evidence_recall_at_{report.profile.top_k}="
            f"{report.evidence_recall_at_k:.2%}"
        )
        print(
            f"evidence_mean_reciprocal_rank={report.evidence_mean_reciprocal_rank:.4f}"
        )
        for category, metrics in report.category_metrics.items():
            print(
                f"category={category} "
                f"questions={metrics['question_count']} "
                f"pass_rate={metrics['pass_rate']:.2%} "
                f"recall_at_k={_format_optional_rate(metrics['evidence_recall_at_k'])}"
            )
        print(
            f"clarification_candidate_recall_at_{report.profile.top_k}="
            f"{report.clarification_candidate_recall_at_k:.2%}"
        )
        print(f"clarification_response_rate={report.clarification_response_rate:.2%}")
        print(f"multi_chunk_pass_rate={report.multi_chunk_pass_rate:.2%}")
        print(f"scope_isolation_pass_rate={report.scope_isolation_pass_rate:.2%}")
        print(f"unanswerable_rejection_rate={report.unanswerable_rejection_rate:.2%}")
        print(f"citation_integrity_pass_rate={report.citation_integrity_pass_rate:.2%}")
        print(f"pdf_page_metadata_pass_rate={report.pdf_page_metadata_pass_rate:.2%}")
        print(f"deletion_passed={str(report.deletion_passed).lower()}")
        print(f"bad_case_count={report.bad_case_count}")
        for question in report.question_results:
            if not question["passed"]:
                print(
                    f"bad_case={question['id']} "
                    f"reasons={','.join(question['failures'])}"
                )
        if report.failed_checks:
            print(f"failed_checks={','.join(report.failed_checks)}")
    return 0 if report.passed else 1


def _format_optional_rate(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2%}"


if __name__ == "__main__":
    raise SystemExit(main())
