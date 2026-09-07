"""Run the frozen R6 bounded-routing evaluation without external providers."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.r6_routing_evaluation import (  # noqa: E402
    run_r6_routing_evaluation,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        help="Write the machine-readable report to this path.",
    )
    parser.add_argument(
        "--legacy-v1-regressions",
        type=int,
        required=True,
        help="Observed V1 answer regressions from the completed quality gate.",
    )
    parser.add_argument(
        "--quality-gate-evidence",
        required=True,
        help="Concise, non-secret evidence identifying that quality-gate run.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the complete machine-readable report.",
    )
    arguments = parser.parse_args()
    if arguments.legacy_v1_regressions < 0:
        parser.error("--legacy-v1-regressions must not be negative")

    report = run_r6_routing_evaluation(
        PROJECT_ROOT,
        implementation_commit=_current_commit(),
        legacy_v1_answer_regressions=arguments.legacy_v1_regressions,
        quality_gate_evidence=arguments.quality_gate_evidence,
    )
    serialized = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if arguments.output is not None:
        output_path = arguments.output
        if not output_path.is_absolute():
            output_path = PROJECT_ROOT / output_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(serialized, encoding="utf-8")

    if arguments.json:
        print(serialized, end="")
    else:
        routing = report["routing"]
        retry = report["retry"]
        print(f"r6_evaluation_passed={str(report['passed']).lower()}")
        print(
            "routing="
            f"{routing['correct_count']}/{routing['sample_count']} "
            f"accuracy:{routing['accuracy']:.2%} "
            f"macro_f1:{routing['macro_f1']:.4f}"
        )
        print(
            "retry="
            f"{retry['correct_count']}/{retry['case_count']} "
            f"accuracy:{retry['accuracy']:.2%} "
            f"precision:{retry['retry_precision']:.4f} "
            f"recall:{retry['retry_recall']:.4f}"
        )
        print(
            "safety="
            f"business_direct_violations:"
            f"{routing['business_fact_direct_answer_violation_count']} "
            f"call_limit_breaches:"
            f"{report['constraints']['retrieval_call_limit_breach_count']} "
            f"scope_violations:"
            f"{report['constraints']['document_scope_violation_count']}"
        )
        if report["failed_checks"]:
            print(f"failed_checks={','.join(report['failed_checks'])}")
    return 0 if report["passed"] else 1


def _current_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


if __name__ == "__main__":
    raise SystemExit(main())
