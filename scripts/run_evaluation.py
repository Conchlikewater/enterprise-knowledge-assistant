"""Run the offline portfolio evaluation and exit non-zero when a gate fails."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.runner import run_evaluation


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
        print(f"top5_source_accuracy={report.top5_source_accuracy:.2%}")
        print(f"multi_chunk_pass_rate={report.multi_chunk_pass_rate:.2%}")
        print(f"scope_isolation_pass_rate={report.scope_isolation_pass_rate:.2%}")
        print(
            "unanswerable_rejection_rate="
            f"{report.unanswerable_rejection_rate:.2%}"
        )
        print(
            "citation_integrity_pass_rate="
            f"{report.citation_integrity_pass_rate:.2%}"
        )
        print(
            "pdf_page_metadata_pass_rate="
            f"{report.pdf_page_metadata_pass_rate:.2%}"
        )
        print(f"deletion_passed={str(report.deletion_passed).lower()}")
        if report.failed_checks:
            print(f"failed_checks={','.join(report.failed_checks)}")
            for question in report.question_results:
                if not question["passed"]:
                    print(
                        f"failed_question={question['id']} "
                        f"reasons={','.join(question['failures'])}"
                    )
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
