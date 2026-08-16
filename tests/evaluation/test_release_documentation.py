from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (PROJECT_ROOT / path).read_text(encoding="utf-8")


def test_primary_documentation_uses_current_v2_evidence() -> None:
    readme = _read("README.md")
    scope = _read("docs/mvp_scope.md")
    release = _read("docs/v2_evaluation_release.md")
    checklist = _read("docs/release_checklist.md")

    assert "10 份合成文档、50 道题" in readme
    assert "Recall 从 100% 降至 92.50%" in readme
    assert "Evaluate 50 typed questions" in scope
    assert "152 passed plus 34 subtests" in release
    assert "Semantic Dense Recall@5 / MRR | 100% / 0.9833" in release
    assert "Semantic Hybrid Recall@5 / MRR | 92.50% / 0.8438" in release
    assert "- [x] create and publish the standalone GitHub repository" in checklist
    assert "152 automated tests pass" in checklist
    assert "2932451552-beep/enterprise-knowledge-assistant" in release
    assert "2932451552-beep/enterprise-knowledge-assistant" in checklist


def test_interview_guide_no_longer_presents_v1_counts_as_current() -> None:
    guide = _read("docs/rag_learning_and_interview_guide.md")

    assert "152 passed" in guide
    assert "50个问题" in guide
    assert "143 passed" not in guide
    assert "84 passed" not in guide
    assert "10份文档和20个问题" not in guide
    assert "Recall@5为100%、MRR为0.9833" in guide
