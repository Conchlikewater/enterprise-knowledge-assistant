"""Run the complete local quality gate with the active Python interpreter."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

CHECKS = (
    (
        "tests",
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-W",
        "error",
    ),
    ("dependencies", sys.executable, "-m", "pip", "check"),
    (
        "bytecode",
        sys.executable,
        "-m",
        "compileall",
        "-q",
        "app",
        "evaluation",
        "scripts",
        "tests",
    ),
    ("offline-evaluation", sys.executable, "scripts/run_evaluation.py"),
)


def main() -> int:
    for name, *command in CHECKS:
        print(f"quality_check_started={name}", flush=True)
        completed = subprocess.run(command, cwd=PROJECT_ROOT, check=False)
        if completed.returncode != 0:
            print(
                f"quality_check_failed={name} exit_code={completed.returncode}",
                flush=True,
            )
            return completed.returncode
        print(f"quality_check_passed={name}", flush=True)
    print("quality_gate_passed=true", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
