"""Build the frozen R7 school-corpus PDF fixtures and hash manifest."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from textwrap import wrap

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = PROJECT_ROOT / "evaluation" / "r7" / "corpus_sources.json"
OUTPUT_DIRECTORY = PROJECT_ROOT / "evaluation" / "r7" / "documents"
MANIFEST_PATH = PROJECT_ROOT / "evaluation" / "r7" / "corpus_manifest.json"


def build_corpus() -> list[Path]:
    source = json.loads(SOURCE_PATH.read_text(encoding="utf-8"))
    OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)

    generated_paths: list[Path] = []
    manifest_documents: list[dict[str, object]] = []
    for document in source["documents"]:
        output_path = OUTPUT_DIRECTORY / document["filename"]
        _write_pdf(output_path, document["pages"], document["source_url"])
        digest = hashlib.sha256(output_path.read_bytes()).hexdigest()
        generated_paths.append(output_path)
        manifest_documents.append(
            {
                "source_id": document["source_id"],
                "filename": document["filename"],
                "source_url": document["source_url"],
                "page_count": len(document["pages"]),
                "sha256": digest,
            }
        )

    manifest = {
        "schema_version": "r7-school-corpus-manifest-v1",
        "status": "frozen_before_graph_implementation",
        "frozen_at": source["frozen_at"],
        "source_manifest_sha256": hashlib.sha256(SOURCE_PATH.read_bytes()).hexdigest(),
        "document_count": len(manifest_documents),
        "documents": manifest_documents,
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return generated_paths


def _write_pdf(output_path: Path, pages: list[str], source_url: str) -> None:
    writer = PdfWriter()
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    font_reference = writer._add_object(font)

    attributed_pages = [*pages]
    attributed_pages[-1] = (
        f"{attributed_pages[-1]}\n\nSource: {source_url}\n"
        "License: https://creativecommons.org/licenses/by-nc-sa/4.0/"
    )
    for page_text in attributed_pages:
        page = writer.add_blank_page(width=612, height=792)
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_reference})}
        )
        lines: list[str] = []
        for paragraph in page_text.split("\n"):
            lines.extend(wrap(paragraph, width=82) or [""])
        operators = ["BT /F1 10 Tf 72 730 Td 14 TL"]
        for line in lines:
            escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            operators.append(f"({escaped}) Tj T*")
        operators.append("ET")
        content = DecodedStreamObject()
        content.set_data("\n".join(operators).encode("ascii"))
        page[NameObject("/Contents")] = writer._add_object(content)

    writer.add_metadata(
        {
            "/Title": output_path.stem,
            "/Producer": "Enterprise Knowledge Assistant R7 fixture builder",
            "/Subject": "CC BY-NC-SA 4.0 noncommercial evaluation fixture",
        }
    )
    with output_path.open("wb") as target:
        writer.write(target)


if __name__ == "__main__":
    paths = build_corpus()
    print(f"r7_corpus_built={len(paths)} manifest={MANIFEST_PATH}")
