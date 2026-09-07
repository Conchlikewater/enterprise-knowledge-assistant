"""Opt-in development calibration; default invocation is a no-network dry run."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import Settings  # noqa: E402
from evaluation.r7_calibration import prepare_inputs, run_calibration  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-paid", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--cache", type=Path)
    arguments = parser.parse_args()
    root = PROJECT_ROOT / "evaluation" / "r7"
    _, _, _, plan = prepare_inputs(root)
    print(json.dumps(plan, indent=2))
    if not arguments.allow_paid:
        print("dry_run=true network_calls=0")
        return 0
    if arguments.output is None or arguments.cache is None:
        parser.error("Paid runs require new --output and --cache paths")
    if arguments.output.exists() or arguments.cache.exists():
        parser.error("Run paths already exist; no calls made")
    settings = Settings.from_env(env_file=PROJECT_ROOT / ".env")
    if not settings.openai_api_key:
        print("calibration_error=missing_openai_key")
        return 1
    from openai import OpenAI

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    with OpenAI(
        api_key=settings.openai_api_key,
        base_url="https://api.openai.com/v1",
        max_retries=0,
        timeout=30.0,
    ) as client:
        report = run_calibration(root, client, arguments.output, arguments.cache)
    print(
        json.dumps(
            {
                k: report[k]
                for k in (
                    "status",
                    "attempted_requests",
                    "reported_total_tokens",
                    "reported_cost_usd",
                )
            }
        )
    )
    print(f"report={arguments.output}")
    return 0 if report["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
