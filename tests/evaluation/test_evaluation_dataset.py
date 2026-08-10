import json
from pathlib import Path

from pypdf import PdfReader

from evaluation.contracts import load_question_contracts

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_evaluation_dataset_matches_architecture_requirements() -> None:
    corpus = json.loads(
        (PROJECT_ROOT / "evaluation" / "corpus_sources.json").read_text(
            encoding="utf-8"
        )
    )["documents"]
    questions = load_question_contracts(PROJECT_ROOT / "evaluation" / "questions.json")

    assert len(corpus) == 10
    assert sum(item["media_type"] == "text/plain" for item in corpus) >= 4
    assert sum(item["media_type"] == "application/pdf" for item in corpus) >= 4
    assert sum(len(item["pages"]) > 1 for item in corpus) >= 2
    assert len(questions) == 50

    category_counts = {
        category: sum(item.category == category for item in questions)
        for category in {item.category for item in questions}
    }
    assert category_counts == {
        "direct": 14,
        "multi_chunk": 6,
        "scope_isolation": 4,
        "unanswerable": 8,
        "paraphrase": 6,
        "distractor": 6,
        "low_score": 4,
        "ambiguous": 2,
    }
    assert all(
        question.expected_answer and question.expected_evidence
        for question in questions
        if question.expected_behavior == "answer"
    )
    assert all(
        question.expected_answer is None and not question.expected_evidence
        for question in questions
        if question.expected_behavior == "refuse"
    )
    assert all(
        question.expected_answer is None and len(question.expected_evidence) >= 2
        for question in questions
        if question.expected_behavior == "clarify"
    )


def test_generated_documents_exist_and_pdf_pages_are_extractable() -> None:
    corpus = json.loads(
        (PROJECT_ROOT / "evaluation" / "corpus_sources.json").read_text(
            encoding="utf-8"
        )
    )["documents"]

    for document in corpus:
        file_path = PROJECT_ROOT / "evaluation" / "documents" / document["filename"]
        assert file_path.is_file()
        assert file_path.stat().st_size > 0
        if document["media_type"] == "application/pdf":
            reader = PdfReader(file_path)
            assert len(reader.pages) == len(document["pages"])
            assert all((page.extract_text() or "").strip() for page in reader.pages)
