import pytest

from evaluation.runner import EvaluationConfig


def test_default_evaluation_config_matches_tracked_baseline() -> None:
    config = EvaluationConfig()

    assert config.name == "baseline"
    assert config.chunk_size == 220
    assert config.chunk_overlap == 30
    assert config.top_k == 5
    assert config.unanswerable_score_threshold == 0.25
    assert config.ambiguity_score_margin == 0.05


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"name": " "}, "name"),
        ({"chunk_size": 0}, "chunk_size"),
        ({"chunk_size": 100, "chunk_overlap": 100}, "chunk_overlap"),
        ({"top_k": 0}, "top_k"),
        ({"top_k": 51}, "top_k"),
        ({"unanswerable_score_threshold": 1.1}, "score_threshold"),
        ({"ambiguity_score_margin": -0.1}, "ambiguity_score_margin"),
    ],
)
def test_evaluation_config_rejects_invalid_values(
    overrides: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        EvaluationConfig(**overrides)  # type: ignore[arg-type]
