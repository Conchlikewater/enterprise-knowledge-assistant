import hashlib
import json
from pathlib import Path

import pytest

from app.document_processing.loaders import DocumentSection
from evaluation.r7_chunk_readiness import inspect_local_sources, inspect_sections


def test_diagnostic_locators_are_repeatable_without_exporting_text() -> None:
    sections = [DocumentSection("CODE-1\n先修课程：编程\nPRIVATE_PERSON_123", 1)]
    first = inspect_sections(sections, "source-a", "a" * 64, "CODE-1")
    assert first == inspect_sections(sections, "source-a", "a" * 64, "CODE-1")
    assert first["code_and_marker_share_chunk"] is True
    assert "PRIVATE_PERSON_123" not in json.dumps(first)
    assert "编程" not in json.dumps(first, ensure_ascii=False)
    assert set(first["prerequisite_marker_locators"][0]) == {
        "page_number",
        "chunk_index",
        "content_sha256",
    }


def test_code_and_field_label_in_different_chunks_are_not_colocated() -> None:
    text = "CODE-1\n" + "x" * 90 + "\n先修课程：编程"
    report = inspect_sections(
        [DocumentSection(text, 1)], "s", "a" * 64, "CODE-1", 40, 0
    )
    assert report["course_code_found_on_page_one"] is True
    assert report["prerequisite_marker_found_on_page_one"] is True
    assert report["code_and_marker_share_chunk"] is False


def test_other_page_or_missing_code_does_not_imply_page_one_identity() -> None:
    sections = [DocumentSection("先修课程", 1), DocumentSection("CODE-1", 2)]
    report = inspect_sections(sections, "s", "a" * 64, "CODE-1")
    assert report["course_code_found_on_page_one"] is False
    assert report["code_and_marker_share_chunk"] is False
    assert (
        inspect_sections(sections, "s", "a" * 64, None)["course_code_available"]
        is False
    )


def _inputs(
    tmp_path: Path, source_id: str = "source-a", digest: str | None = None
) -> tuple[Path, Path]:
    root, raw = tmp_path / "metadata", tmp_path / "raw"
    root.mkdir()
    raw.mkdir()
    (raw / "source-a.pdf").write_bytes(b"fake-pdf")
    source = {
        "id": source_id,
        "sha256": digest or hashlib.sha256(b"fake-pdf").hexdigest(),
    }
    (root / "neuq_2023_source_lock.json").write_text(
        json.dumps({"documents": [source]}), encoding="utf-8"
    )
    (root / "neuq_2023_ce_source_lock.json").write_text(
        json.dumps({"documents": []}), encoding="utf-8"
    )
    (root / "neuq_2023_relation_candidates.json").write_text(
        json.dumps({"nodes": []}), encoding="utf-8"
    )
    return root, raw


@pytest.mark.parametrize(
    "source_id,digest", [("source-a", "0" * 64), ("../source-a", None)]
)
def test_bad_source_is_rejected_before_parsing(
    tmp_path, monkeypatch, source_id, digest
) -> None:
    root, raw = _inputs(tmp_path, source_id, digest)

    def forbidden_parse(_):
        pytest.fail("Invalid source must not be parsed")

    monkeypatch.setattr("evaluation.r7_chunk_readiness.load_pdf", forbidden_parse)
    with pytest.raises(ValueError, match="Source missing, unsafe or hash mismatched"):
        inspect_local_sources(root, raw)


def test_only_source_metadata_is_read_no_questions_or_secrets(
    tmp_path, monkeypatch
) -> None:
    root, raw = _inputs(tmp_path)
    original = Path.read_text
    read_names = []

    def guarded_read(path, *args, **kwargs):
        read_names.append(path.name)
        assert "question" not in path.name and path.name != ".env"
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", guarded_read)
    monkeypatch.setattr(
        "evaluation.r7_chunk_readiness.load_pdf",
        lambda _: [DocumentSection("先修课程：无", 1)],
    )
    report = inspect_local_sources(root, raw)
    assert len(read_names) == 3
    assert report["summary"]["documents"] == 1
    assert report["provider_calls"] == 0
    assert report["formal_chunk_ids_assigned"] is False
    assert report["profile"]["origin"] == "historical_r7_profile_not_frozen_for_neuq"
