"""Build a local, source-wide R7 corpus candidate without exporting raw PDFs.

The output remains local and unapproved until its manifest and representative
rendered pages are reviewed. This deterministic filter is deliberately
conservative: page one is reconstructed from reviewed structural facts; later
administrative content and personnel-bearing lines are dropped. It does not use
questions, Gold annotations, retrieval scores, providers or application stores.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from pypdf import PdfReader

from evaluation.r7_corpus_contract import ReviewedBlock, review_digest

SECTION_MARKERS = (
    ("learning_objectives", ("二、教学目标", "subjectlearningobjectives")),
    ("teaching_content", ("三、教学内容",)),
    ("teaching_schedule", ("四、教学安排", "学时分配")),
    ("teaching_method", ("五、教学方法",)),
    ("assessment", ("六、成绩评定", "assessment")),
    ("administrative", ("七、其他", "七、改进机制", "教学大纲改进机制")),
)
PERSONNEL_MARKERS = (
    "任课教师",
    "中方课程协调人",
    "课程协调人",
    "课程负责人",
    "环节负责人",
    "撰写",
    "审核人",
    "批准人",
    "taughtby",
    "coordinator",
    "subjectdirector",
    "checkedby",
    "approvedby",
    "director",
)
PAGE_ONE_PERSONNEL_MARKERS = (
    "任课教师",
    "中方课程协调人",
    "课程协调人",
    "课程负责人",
    "撰写",
    "审核人",
    "批准人",
    "taughtby",
    "coordinator",
    "subjectdirector",
    "checkedby",
    "approvedby",
)
_FOOTER = re.compile(r"^\s*\d+\s*/\s*\d+\s*$")
_URL = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
_EMAIL = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")


@dataclass(frozen=True)
class CandidatePage:
    source_id: str
    source_sha256: str
    page_number: int
    decision: str
    block_ids: tuple[str, ...]
    exclusion_reason: str | None
    extracted_text_sha256: str
    redacted_line_count: int


def _compact(text: str) -> str:
    return "".join(text.split()).casefold()


def _layout(page) -> str:
    try:
        return page.extract_text(extraction_mode="layout") or ""
    except Exception:
        return page.extract_text() or ""


def _sensitive_terms(readers: list[PdfReader]) -> tuple[str, ...]:
    """Extract local-only tokens from labelled personnel rows; never export them."""
    zones = []
    for reader in readers:
        for line in _layout(reader.pages[0]).splitlines():
            compact = _compact(line)
            positions = [
                compact.find(marker)
                for marker in PAGE_ONE_PERSONNEL_MARKERS
                if marker in compact
            ]
            if not positions:
                continue
            marker_position = min(positions)
            raw_positions = [
                index for index, char in enumerate(line) if not char.isspace()
            ]
            zones.append(line[raw_positions[marker_position] :])
    candidates = set()
    stop = {
        "任课教师",
        "含负责人",
        "中方课程协调人",
        "课程负责人",
        "撰写人",
        "审核人",
        "批准人",
        "课程",
        "负责人",
        "提交日期",
        "成绩记载方式",
        "百分制",
        "五级制",
        "平时",
        "期中",
        "期末",
        "实验",
        "考核环节",
        "单击或点击此处输入日期",
        "taught",
        "by",
        "coordinator",
        "subject",
        "director",
        "checked",
        "approved",
        "submitted",
        "date",
        "result",
        "type",
        "marks",
        "none",
        "the",
        "and",
    }
    for zone in zones:
        for token in re.findall(r"[\u4e00-\u9fff]{2,8}", zone):
            if token.casefold() not in stop and not any(
                m in token.casefold() for m in PERSONNEL_MARKERS
            ):
                candidates.add(token.casefold())
        for token in re.findall(r"[A-Z][A-Za-z.'-]{2,}", zone):
            if token.casefold() not in stop and len(token) >= 4:
                candidates.add(token.casefold())
    return tuple(sorted(candidates, key=lambda value: (-len(value), value)))


def _section(line: str) -> str | None:
    compact = _compact(line)
    for kind, markers in SECTION_MARKERS:
        if any(_compact(marker) in compact for marker in markers):
            return kind
    return None


def _sanitize_line(line: str, sensitive_terms: tuple[str, ...]) -> tuple[str, bool]:
    line = " ".join(line.split())
    if not line or _FOOTER.fullmatch(line):
        return "", False
    compact = _compact(line)
    redacted = False
    indexes = [
        compact.find(marker) for marker in PERSONNEL_MARKERS if marker in compact
    ]
    if indexes:
        redacted = True
        # Layout extraction keeps table columns on one line. Preserve only the
        # safe left-hand cell, never the personnel marker or its value.
        marker_position = min(indexes)
        positions = [index for index, char in enumerate(line) if not char.isspace()]
        raw_position = positions[marker_position]
        line = line[:raw_position].strip(" :：|-")
        compact = _compact(line)
        if not line:
            return "", True
    line = _URL.sub("", _EMAIL.sub("", line)).strip()
    compact = _compact(line)
    if not line or any(term in compact for term in sensitive_terms):
        return "", True
    return line, redacted


def _fact_blocks(fact: dict) -> list[ReviewedBlock]:
    values = [
        f"课程名称：{fact['course_title']}",
        f"课程编号：{fact['course_code']}",
        f"学分：{fact['credits']}",
        f"开课学期：{fact['semester']}",
        f"总学时或周数：{fact['total_hours']}",
        f"理论学时：{fact['lecture_hours']}",
        f"实验学时：{fact['lab_hours']}",
        f"课程属性：{fact['course_attribute']}",
        f"成绩记载方式：{fact['result_type']}",
    ]
    if fact["course_mode"]:
        values.append(f"课程模式：{fact['course_mode']}")
    if fact["catalogue_memberships"]:
        values.append("来源目录专业：" + "、".join(fact["catalogue_memberships"]))
    if fact["reviewed_applicable_programs"]:
        values.append(
            "大纲明确适用专业：" + "、".join(fact["reviewed_applicable_programs"])
        )
    if fact["prerequisite_declaration"] == "explicit_none":
        prerequisite = "先修课程：原表明确写无。"
    elif fact["prerequisite_declaration"] == "blank_not_explicit_none":
        prerequisite = "先修课程：原表未填写；不能据此认定明确无先修。"
    elif (
        fact["prerequisite_declaration"] == "stated_list_or_name"
        and fact["prerequisite_text"]
    ):
        prerequisite = "先修课程：" + fact["prerequisite_text"]
    else:
        raise ValueError("Invalid prerequisite declaration")
    common = dict(
        source_id=fact["source_id"],
        source_sha256=fact["source_sha256"],
        page_number=1,
        course_title=fact["course_title"],
        course_code=fact["course_code"],
    )
    return [
        ReviewedBlock(
            block_id="course-information",
            kind="course_information",
            text="。".join(values) + "。",
            **common,
        ),
        ReviewedBlock(
            block_id="prerequisites", kind="prerequisites", text=prerequisite, **common
        ),
    ]


def build_candidate(r7_root: Path, raw_root: Path, fact_path: Path) -> dict:
    lock_names = ("neuq_2023_source_lock.json", "neuq_2023_ce_source_lock.json")
    selected, lock_hashes = [], {}
    for index, name in enumerate(lock_names):
        raw = (r7_root / name).read_bytes()
        lock_hashes[name] = hashlib.sha256(raw).hexdigest()
        selected.extend(
            d
            for d in json.loads(raw)["documents"]
            if index == 0 or d["selected_for_candidate_work"]
        )
    facts_raw = fact_path.read_bytes()
    facts = json.loads(facts_raw)
    by_fact = {f["source_id"]: f for f in facts["documents"]}
    if len(selected) != len(by_fact) or {d["id"] for d in selected} != by_fact.keys():
        raise ValueError("Course facts do not cover the selected corpus")
    raw_root = raw_root.resolve()
    inputs = []
    for source in selected:
        path = (raw_root / f"{source['id']}.pdf").resolve()
        if (
            path.parent != raw_root
            or not path.is_file()
            or hashlib.sha256(path.read_bytes()).hexdigest() != source["sha256"]
        ):
            raise ValueError("Source missing, unsafe or hash mismatched")
        reader = PdfReader(path)
        if reader.is_encrypted or len(reader.pages) != source["pages"]:
            raise ValueError("Source page count changed")
        inputs.append((source, reader))
    terms = _sensitive_terms([reader for _, reader in inputs])
    blocks, decisions = [], []
    for source, reader in sorted(inputs, key=lambda item: item[0]["id"]):
        page_blocks = _fact_blocks(by_fact[source["id"]])
        blocks.extend(page_blocks)
        decisions.append(
            CandidatePage(
                source["id"],
                source["sha256"],
                1,
                "keep",
                tuple(b.block_id for b in page_blocks),
                None,
                hashlib.sha256(_layout(reader.pages[0]).encode()).hexdigest(),
                0,
            )
        )
        current = "learning_objectives"
        administrative = False
        content_started = False
        for number, page in enumerate(reader.pages[1:], 2):
            raw_text = _layout(page)
            segments: list[tuple[str, list[str]]] = []
            redacted = 0
            for raw_line in raw_text.splitlines():
                new_section = _section(raw_line)
                if new_section == "administrative":
                    administrative = True
                    break
                if new_section:
                    current = new_section
                    content_started = True
                if administrative:
                    break
                if not content_started:
                    continue
                line, removed = _sanitize_line(raw_line, terms)
                redacted += removed
                if not line:
                    continue
                if not segments or segments[-1][0] != current:
                    segments.append((current, []))
                segments[-1][1].append(line)
            safe_blocks = []
            for index, (kind, lines) in enumerate(segments, 1):
                text = "\n".join(lines).strip()
                if not text:
                    continue
                safe_blocks.append(
                    ReviewedBlock(
                        source_id=source["id"],
                        source_sha256=source["sha256"],
                        page_number=number,
                        block_id=f"{kind}-{index}",
                        kind=kind,
                        course_title=by_fact[source["id"]]["course_title"],
                        course_code=by_fact[source["id"]]["course_code"],
                        text=text,
                    )
                )
            blocks.extend(safe_blocks)
            if safe_blocks:
                decision, reason = "keep", None
            else:
                decision, reason = (
                    "exclude",
                    "administrative_only"
                    if administrative
                    else "no_structural_content",
                )
            decisions.append(
                CandidatePage(
                    source["id"],
                    source["sha256"],
                    number,
                    decision,
                    tuple(b.block_id for b in safe_blocks),
                    reason,
                    hashlib.sha256(raw_text.encode()).hexdigest(),
                    redacted,
                )
            )
    serialized_blocks = [asdict(b) for b in blocks]
    return {
        "schema_version": "r7-safe-corpus-candidate-v1",
        "status": "local_candidate_pending_review",
        "source_lock_hashes": lock_hashes,
        "course_facts_sha256": hashlib.sha256(facts_raw).hexdigest(),
        "implementation_sha256": hashlib.sha256(
            Path(__file__).read_bytes()
        ).hexdigest(),
        "question_files_loaded": False,
        "gold_loaded": False,
        "provider_calls": 0,
        "raw_pdf_text_exported": False,
        "sensitive_term_count_not_exported": len(terms),
        "summary": {
            "documents": len(selected),
            "pages": len(decisions),
            "kept_pages": sum(d.decision == "keep" for d in decisions),
            "excluded_pages": sum(d.decision == "exclude" for d in decisions),
            "blocks": len(blocks),
            "characters": sum(len(b.text) for b in blocks),
            "redacted_lines": sum(d.redacted_line_count for d in decisions),
            "remaining_personnel_marker_blocks": sum(
                any(m in _compact(b.text) for m in PERSONNEL_MARKERS) for b in blocks
            ),
            "remaining_local_sensitive_term_blocks": sum(
                any(t in _compact(b.text) for t in terms) for b in blocks
            ),
            "privacy_approved": False,
        },
        "page_decisions": [asdict(d) for d in decisions],
        "block_reviews": [
            {
                "source_id": b.source_id,
                "page_number": b.page_number,
                "block_id": b.block_id,
                "candidate_review_digest": review_digest(b),
                "review_status": "pending",
            }
            for b in blocks
        ],
        "blocks": serialized_blocks,
        "limitations": [
            "The local file contains sanitized candidate text and must remain ignored until review.",
            "Personnel-term derivation is local-only and is not proof that every possible name was found.",
            "Page-one facts are paraphrased uniformly; later text remains a local filtered derivative and is not committed.",
            "No parameter selection, Gold mapping, embedding or graph retrieval was performed.",
        ],
    }


def manifest(candidate: dict) -> dict:
    result = {k: v for k, v in candidate.items() if k != "blocks"}
    result["local_candidate_sha256"] = hashlib.sha256(
        json.dumps(
            candidate, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()
    result["candidate_corpus_sha256"] = hashlib.sha256(
        json.dumps(
            candidate["blocks"],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--facts", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    candidate = build_candidate(
        Path(__file__).resolve().parent / "r7", args.raw_dir, args.facts
    )
    args.output.write_text(
        json.dumps(candidate, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if args.manifest:
        args.manifest.write_text(
            json.dumps(manifest(candidate), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
