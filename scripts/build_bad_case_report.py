"""Build the tracked V2 bad-case catalogue from completed reports."""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.bad_cases import build_bad_case_report  # noqa: E402


def main() -> int:
    report = build_bad_case_report(PROJECT_ROOT)
    output_path = PROJECT_ROOT / "evaluation" / "bad_case_report.json"
    output_path.write_text(
        json.dumps(report.to_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print("bad_case_report_completed=true")
    for group in report.groups:
        print(
            f"group={group.name} stage={group.failure_stage} "
            f"status={group.status} count={group.count}"
        )
    print(f"report={output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
