"""Plan or explicitly run the hash-bound NEUQ development calibration."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import Settings  # noqa: E402
from evaluation.r7_neuq_calibration import (  # noqa: E402
    prepare_inputs,
    run_calibration,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--allow-paid", action="store_true")
    parser.add_argument("--approval", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--cache", type=Path)
    args = parser.parse_args()
    r7_root = PROJECT_ROOT / "evaluation" / "r7"
    plan = prepare_inputs(r7_root, args.candidate)[-1]
    print(json.dumps(plan, indent=2))
    if not args.allow_paid:
        print("dry_run=true network_calls=0")
        return 0
    if not args.approval or not args.output or not args.cache:
        parser.error("Paid execution requires approval, output and cache paths")
    if args.output.exists() or args.cache.exists():
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
        report = run_calibration(
            r7_root,
            args.candidate,
            args.approval,
            client,
            args.output,
            args.cache,
        )
    print(
        json.dumps(
            {
                key: report[key]
                for key in (
                    "status",
                    "attempted_requests",
                    "reported_total_tokens",
                    "reported_cost_usd",
                )
            }
        )
    )
    print(f"report={args.output}")
    return 0 if report["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
