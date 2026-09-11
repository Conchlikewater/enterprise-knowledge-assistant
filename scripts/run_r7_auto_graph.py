"""Budgeted extraction from admitted structural chunks; independent of question Gold."""

import argparse
import hashlib
import json
import logging
import sys
from dataclasses import asdict
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import Settings  # noqa: E402
from evaluation.experiments.r7_auto_extraction import (  # noqa: E402
    INSTRUCTIONS,
    SourceInput,
    prompt,
    validate_output,
)
from evaluation.experiments.r7_replay import write_new  # noqa: E402
from evaluation.r7_chunk_profile_analysis import (  # noqa: E402
    PREFERRED_PROFILE,
    PROFILE_CANDIDATES,
    _admitted_inputs,
)
from evaluation.r7_corpus_contract import build_complete_corpus  # noqa: E402


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def fingerprint(value):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


def inputs(candidate_path):
    candidate = read(candidate_path)
    admission = read(
        ROOT / "evaluation/r7/preparation/r7b_safe_corpus_admission_20260910.json"
    )
    blocks, snapshots, reviews, decisions = _admitted_inputs(candidate, admission)
    chunks = build_complete_corpus(
        blocks, snapshots, reviews, PROFILE_CANDIDATES[PREFERRED_PROFILE], decisions
    )
    titles = {(b.source_id, b.block_id): b.course_title for b in blocks}
    return sorted(
        [
            SourceInput(
                c.source_id,
                c.source_sha256,
                c.chunk_id,
                c.page_number,
                titles[c.source_id, c.block_id],
                c.text,
            )
            for c in chunks
            if c.kind in {"course_information", "prerequisites"}
        ],
        key=lambda s: (s.document_id, s.chunk_id),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--stage", choices=("smoke", "review"), required=True)
    parser.add_argument("--execute-approved", action="store_true")
    args = parser.parse_args()
    if args.run_dir.exists():
        raise ValueError("Run directory exists; no overwrite or automatic retry")
    sources = inputs(args.candidate)
    ids = sorted({s.document_id for s in sources})
    scope = ids[:4] if args.stage == "smoke" else ids[4:]
    selected = [s for s in sources if s.document_id in scope]
    requests = [(s, prompt(s)) for s in selected]
    upper = sum(len((INSTRUCTIONS + text).encode()) + 512 for _, text in requests)
    cost = (upper * 0.3 + len(requests) * 1536 * 1.2) / 1000000
    if len(ids) != 44 or len(requests) > 88 or cost > 0.4:
        raise ValueError("Extraction plan exceeds scope or budget")
    plan = {
        "model": "deepseek-flash",
        "document_ids": scope,
        "requests": len(requests),
        "stage": args.stage,
        "input_token_upper_bound": upper,
        "max_output_tokens_per_request": 1536,
        "cost_upper_bound_usd": cost,
        "input_usd_per_million": 0.3,
        "output_usd_per_million": 1.2,
        "instruction_sha256": fingerprint(INSTRUCTIONS),
        "source_inputs_sha256": fingerprint([asdict(s) for s in selected]),
        "sdk_retries": 0,
        "temperature": 0,
        "thinking": "disabled",
    }
    print(json.dumps(plan))
    if not args.execute_approved:
        return 0
    settings = Settings.from_env(env_file=ROOT / ".env")
    if not settings.deepseek_api_key:
        print("missing_deepseek_key=true calls=0")
        return 1
    from openai import OpenAI

    args.run_dir.mkdir(parents=True, exist_ok=False)
    write_new(args.run_dir / "plan.json", plan)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    records = []
    with OpenAI(
        api_key=settings.deepseek_api_key,
        base_url="https://api.deepseek.com",
        max_retries=0,
        timeout=60,
    ) as client:
        for index, (source, text) in enumerate(requests):
            record = {"document_id": source.document_id, "chunk_id": source.chunk_id}
            start = perf_counter()
            try:
                response = client.chat.completions.create(
                    model="deepseek-flash",
                    messages=[
                        {"role": "system", "content": INSTRUCTIONS},
                        {"role": "user", "content": text},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0,
                    max_tokens=1536,
                    extra_body={"thinking": {"type": "disabled"}},
                )
                record.update(
                    response_model=response.model,
                    input_tokens=response.usage.prompt_tokens,
                    output_tokens=response.usage.completion_tokens,
                    finish_reason=response.choices[0].finish_reason,
                    raw_output=response.choices[0].message.content,
                )
                if record["finish_reason"] != "stop":
                    raise ValueError("Incomplete model output")
                record["extraction"] = validate_output(record["raw_output"], source)
                record["status"] = "validated_pending_semantic_review"
            except Exception as exc:
                record.update(status="failed", error_type=type(exc).__name__)
            record["latency_ms"] = (perf_counter() - start) * 1000
            records.append(record)
            write_new(args.run_dir / f"chunk_{index:03}.json", record)
            print(
                f"completed={index + 1}/{len(requests)} status={record['status']}",
                flush=True,
            )
            if record["status"] == "failed" and "raw_output" not in record:
                break
    summary = {
        "requests": len(records),
        "planned": len(requests),
        "validated": sum(
            r["status"] == "validated_pending_semantic_review" for r in records
        ),
        "edges": sum(len(r.get("extraction", {}).get("edges", [])) for r in records),
        "input_tokens": sum(r.get("input_tokens", 0) for r in records),
        "output_tokens": sum(r.get("output_tokens", 0) for r in records),
    }
    summary["cost_upper_estimate_usd"] = (
        summary["input_tokens"] * 0.3 + summary["output_tokens"] * 1.2
    ) / 1000000
    write_new(args.run_dir / "summary.json", summary)
    print(json.dumps(summary))
    return 0 if summary["validated"] == len(requests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
