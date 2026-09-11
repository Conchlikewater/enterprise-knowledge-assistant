"""Offline chunk diagnostics, not Gold assignment or retrieval evaluation.

Reads locked local PDFs and source metadata only. Never loads questions, secrets,
providers or stores. Raw text stays in memory and is never included in output.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from app.document_processing.chunker import chunk_sections
from app.document_processing.loaders import DocumentSection, load_pdf


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inspect_sections(
    sections: list[DocumentSection],
    source_id: str,
    source_hash: str,
    course_code: str | None,
    chunk_size: int = 220,
    overlap: int = 30,
) -> dict:
    document_id = uuid5(NAMESPACE_URL, f"r7-chunk-diagnostic:{source_id}:{source_hash}")
    chunks = chunk_sections(
        sections, document_id, f"{source_id}.pdf", chunk_size, overlap
    )
    first_page = [c for c in chunks if c.page_number == 1]

    def normalize(text: str) -> str:
        return "".join(text.split())

    code_hits = [
        c
        for c in first_page
        if course_code and normalize(course_code) in normalize(c.text)
    ]
    marker_hits = [c for c in first_page if "先修课程" in normalize(c.text)]
    # These are locators for field labels, not claims that whole field values fit.
    marker_locators = [
        {
            "page_number": c.page_number,
            "chunk_index": c.chunk_index,
            "content_sha256": c.content_hash,
        }
        for c in marker_hits
    ]
    return {
        "source_id": source_id,
        "source_sha256": source_hash,
        "parsed_nonempty_pages": len(sections),
        "chunk_count": len(chunks),
        "page_one_chunk_count": len(first_page),
        "course_code_available": bool(course_code),
        "course_code_found_on_page_one": bool(code_hits),
        "prerequisite_marker_found_on_page_one": bool(marker_hits),
        "code_and_marker_share_chunk": any(c in code_hits for c in marker_hits),
        "prerequisite_marker_locators": marker_locators,
    }


def inspect_local_sources(r7_root: Path, raw_dir: Path) -> dict:
    lock_names = ("neuq_2023_source_lock.json", "neuq_2023_ce_source_lock.json")
    documents = []
    for i, filename in enumerate(lock_names):
        lock = json.loads((r7_root / filename).read_text(encoding="utf-8"))
        documents.extend(
            d for d in lock["documents"] if i == 0 or d["selected_for_candidate_work"]
        )
    ledger_path = r7_root / "neuq_2023_relation_candidates.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    codes = {
        n["source_id"]: n["course_code"]
        for n in ledger["nodes"]
        if n.get("course_code")
    }
    raw_root = raw_dir.resolve()
    inputs = []
    for d in documents:
        path = (raw_root / f"{d['id']}.pdf").resolve()
        if path.parent != raw_root or not path.is_file() or _hash(path) != d["sha256"]:
            raise ValueError(
                "Source missing, unsafe or hash mismatched; no source accepted"
            )
        inputs.append((d, path))
    rows = [
        inspect_sections(load_pdf(path), d["id"], d["sha256"], codes.get(d["id"]))
        for d, path in inputs
    ]
    code_known = [r for r in rows if r["course_code_available"]]
    return {
        "schema_version": "r7-source-chunk-diagnostic-v1",
        "status": "diagnostic_only_not_gold_not_parameter_selection",
        "profile": {
            "chunk_size": 220,
            "chunk_overlap": 30,
            "origin": "historical_r7_profile_not_frozen_for_neuq",
        },
        "input_hashes": {
            name: _hash(r7_root / name) for name in (*lock_names, ledger_path.name)
        },
        "implementation_hashes": {
            name: _hash(Path(__file__).resolve().parents[1] / name)
            for name in (
                "app/document_processing/loaders.py",
                "app/document_processing/chunker.py",
                "evaluation/r7_chunk_readiness.py",
            )
        },
        "provider_calls": 0,
        "question_files_loaded": False,
        "raw_text_exported": False,
        "formal_chunk_ids_assigned": False,
        "summary": {
            "documents": len(rows),
            "parsed_nonempty_pages": sum(r["parsed_nonempty_pages"] for r in rows),
            "chunks": sum(r["chunk_count"] for r in rows),
            "sources_with_known_course_code": len(code_known),
            "known_codes_found_on_page_one": sum(
                r["course_code_found_on_page_one"] for r in code_known
            ),
            "sources_with_prerequisite_marker": sum(
                r["prerequisite_marker_found_on_page_one"] for r in rows
            ),
            "known_code_and_marker_share_chunk": sum(
                r["code_and_marker_share_chunk"] for r in code_known
            ),
        },
        "limitations": [
            "Field-label presence is not complete field-value evidence or Gold coverage.",
            "Course-code substring matches are diagnostics, not canonical entity resolution.",
            "Do not choose parameters using formal questions or these source diagnostics.",
            "No header injection, redaction pipeline or privacy clearance has been implemented here.",
            "Locators are diagnostic index/hash pairs; production UUIDs are not reused or frozen.",
        ],
        "documents": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent / "r7"
    print(
        json.dumps(
            inspect_local_sources(root, args.raw_dir), ensure_ascii=False, indent=2
        )
    )


if __name__ == "__main__":
    main()
