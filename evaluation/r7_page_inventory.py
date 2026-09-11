"""Source-wide page inventory, without exporting source text or approving privacy."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from pypdf import PdfReader

MARKERS = {
    "course_information": ("课程信息", "subjectinformation"),
    "prerequisites": ("先修课程", "requisites"),
    "learning_objectives": ("教学目标", "learningobjectives"),
    "teaching_content": ("教学内容", "知识单元", "知识点"),
    "teaching_schedule": ("教学安排", "学时分配"),
    "assessment": ("成绩评定", "assessment", "考核方式"),
    "administration": ("改进机制", "improvementmechanism", "批准日期"),
    "bibliography": ("参考教材", "textbooks", "参考文献"),
    "personnel": (
        "任课教师",
        "课程协调人",
        "课程负责人",
        "环节负责人",
        "撰写",
        "审核",
        "批准人",
        "taughtby",
        "coordinator",
        "checkedby",
        "approvedby",
    ),
}


def summarize_page(text: str, page_number: int) -> dict:
    compact = "".join(text.split()).casefold()
    markers = sorted(
        name for name, terms in MARKERS.items() if any(t in compact for t in terms)
    )
    return {
        "page_number": page_number,
        "extracted_text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "character_count": len(text),
        "detected_markers": markers,
        "review_status": "pending",
        "safe_blocks": [],
    }


def inventory_sources(r7_root: Path, raw_root: Path) -> dict:
    names = ("neuq_2023_source_lock.json", "neuq_2023_ce_source_lock.json")
    selected, lock_hashes = [], {}
    for index, name in enumerate(names):
        data = (r7_root / name).read_bytes()
        lock_hashes[name] = hashlib.sha256(data).hexdigest()
        selected.extend(
            d
            for d in json.loads(data)["documents"]
            if index == 0 or d["selected_for_candidate_work"]
        )
    if len({d["id"] for d in selected}) != len(selected):
        raise ValueError("Duplicate source identity")
    checked = []
    raw_root = raw_root.resolve()
    # Verify every source before attempting to parse any of them.
    for source in selected:
        path = (raw_root / f"{source['id']}.pdf").resolve()
        if (
            path.parent != raw_root
            or not path.is_file()
            or hashlib.sha256(path.read_bytes()).hexdigest() != source["sha256"]
        ):
            raise ValueError("Source missing, unsafe or hash mismatched")
        checked.append((source, path))
    documents = []
    for source, path in checked:
        try:
            reader = PdfReader(path)
            if reader.is_encrypted or len(reader.pages) != source["pages"]:
                raise ValueError("PDF snapshot page count mismatch")
            pages = [
                summarize_page(page.extract_text() or "", number)
                for number, page in enumerate(reader.pages, 1)
            ]
        except Exception:
            raise ValueError("Source could not be inventoried safely") from None
        documents.append(
            {
                "source_id": source["id"],
                "source_sha256": source["sha256"],
                "pages": pages,
            }
        )
    pages = [p for d in documents for p in d["pages"]]
    return {
        "schema_version": "r7-page-inventory-v1",
        "status": "automated_structure_inventory_not_privacy_approval",
        "source_lock_hashes": lock_hashes,
        "implementation_sha256": hashlib.sha256(
            Path(__file__).read_bytes()
        ).hexdigest(),
        "question_files_loaded": False,
        "raw_text_exported": False,
        "provider_calls": 0,
        "summary": {
            "documents": len(documents),
            "pages": len(pages),
            "nonempty_pages": sum(p["character_count"] > 0 for p in pages),
            "pages_with_personnel_markers": sum(
                "personnel" in p["detected_markers"] for p in pages
            ),
            "pages_without_recognized_markers": sum(
                not p["detected_markers"] for p in pages
            ),
            "privacy_approved_pages": 0,
        },
        "limitations": [
            "Markers describe page text, not bounding boxes or complete sections.",
            "No marker does not mean no person name; no page is automatically approved.",
            "All selected pages are included; formal questions and Gold are never loaded.",
        ],
        "documents": documents,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, required=True)
    args = parser.parse_args()
    result = inventory_sources(Path(__file__).resolve().parent / "r7", args.raw_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
