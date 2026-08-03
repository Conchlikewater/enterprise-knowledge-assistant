"""Build deterministic TXT/PDF evaluation fixtures from canonical JSON sources."""

from __future__ import annotations

import json
from pathlib import Path
from textwrap import wrap

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = PROJECT_ROOT / "evaluation" / "corpus_sources.json"
OUTPUT_DIRECTORY = PROJECT_ROOT / "evaluation" / "documents"


def build_corpus() -> list[Path]:
    payload = json.loads(SOURCE_PATH.read_text(encoding="utf-8"))
    documents = payload["documents"]
    OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)

    generated_paths: list[Path] = []
    for document in documents:
        filename = document["filename"]
        pages = document["pages"]
        output_path = OUTPUT_DIRECTORY / filename
        if document["media_type"] == "text/plain":
            output_path.write_text("\n\n".join(pages) + "\n", encoding="utf-8")
        elif document["media_type"] == "application/pdf":
            _write_pdf(output_path, pages)
        else:
            raise ValueError(f"unsupported fixture media type for {filename}")
        generated_paths.append(output_path)

    return generated_paths


def _write_pdf(output_path: Path, pages: list[str]) -> None:
    writer = PdfWriter()
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    font_reference = writer._add_object(font)

    for page_text in pages:
        page = writer.add_blank_page(width=612, height=792)
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_reference})}
        )
        lines = []
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

    writer.add_metadata({"/Title": output_path.stem, "/Producer": "RAG V1 evaluator"})
    with output_path.open("wb") as target:
        writer.write(target)


if __name__ == "__main__":
    paths = build_corpus()
    print(f"evaluation_corpus_built={len(paths)} directory={OUTPUT_DIRECTORY}")
