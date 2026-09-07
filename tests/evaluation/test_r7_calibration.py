import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from evaluation.r7_calibration import (
    DIMENSIONS,
    MODEL,
    MeteredClient,
    cosine,
    prepare_inputs,
    run_calibration,
    select_threshold,
)

ROOT = Path(__file__).resolve().parents[2] / "evaluation" / "r7"
POLICY = {
    "threshold_candidate_min": 0.2,
    "threshold_candidate_max": 0.6,
    "threshold_candidate_step": 0.01,
}


class FakeClient:
    def __init__(self, failure=False):
        self.embeddings = self
        self.calls = []
        self.failure = failure

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.failure:
            raise RuntimeError("secret-like-provider-body-must-not-be-recorded")
        return SimpleNamespace(
            data=[
                SimpleNamespace(index=i, embedding=[1.0] + [0.0] * (DIMENSIONS - 1))
                for i in reversed(range(len(kwargs["input"])))
            ],
            model=MODEL,
            usage=SimpleNamespace(prompt_tokens=10, total_tokens=10),
        )


def test_calibration_never_reads_final_questions(monkeypatch):
    original = Path.read_text

    def guarded(path, *args, **kwargs):
        assert path.name != "questions.json"
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", guarded)
    _, chunks, questions, plan = prepare_inputs(ROOT)
    assert len(chunks) == 92
    assert len(questions) == 10
    assert plan["requests_planned"] == 3
    assert plan["input_token_upper_bound"] <= 20_000
    assert plan["estimated_cost_upper_bound_usd"] < 0.01
    assert len({chunk.chunk_id for chunk in chunks}) == len(chunks)
    assert [c.chunk_id for c in chunks] == [c.chunk_id for c in prepare_inputs(ROOT)[1]]


def test_threshold_selects_registered_objective_then_lowest_tie():
    rankings = [
        {"answerable": True, "top5": [{"score": 0.55, "matches_gold": True}]},
        {
            "answerable": False,
            "top5": [
                {"score": 0.4, "matches_gold": False},
                {"score": 0.3, "matches_gold": False},
            ],
        },
    ]
    result = select_threshold(rankings, POLICY)
    assert result["selected_threshold"] == 0.31
    assert len(result["candidate_scan"]) == 41
    assert result["selected_row"]["unsupported_with_fewer_than_two"] == 1


def test_no_eligible_threshold_is_reported_without_changing_range():
    rankings = [
        {"answerable": True, "top5": [{"score": 0.19, "matches_gold": True}]},
        {"answerable": False, "top5": []},
    ]
    result = select_threshold(rankings, POLICY)
    assert result["status"] == "no_eligible_threshold"
    assert result["selected_threshold"] is None


def test_budget_and_model_checks_prevent_requests():
    client = FakeClient()
    meter = MeteredClient(client)
    with pytest.raises(ValueError, match="approved limits"):
        meter.create(input=["x" * 20_001], model=MODEL, dimensions=DIMENSIONS)
    with pytest.raises(ValueError, match="approved limits"):
        meter.create(input=["x"], model="unapproved-model", dimensions=DIMENSIONS)
    assert not client.calls
    for _ in range(3):
        meter.create(input=["x"], model=MODEL, dimensions=DIMENSIONS)
    with pytest.raises(ValueError, match="approved limits"):
        meter.create(input=["x"], model=MODEL, dimensions=DIMENSIONS)
    assert len(client.calls) == 3


def test_failed_attempt_consumes_budget_without_recording_error_body():
    meter = MeteredClient(FakeClient(failure=True))
    with pytest.raises(RuntimeError):
        meter.create(input=["test"], model=MODEL, dimensions=DIMENSIONS)
    assert meter.attempt_count == 1
    assert meter.submitted_token_upper_bound == 4
    assert meter.receipts[0]["status"] == "failed"
    assert "secret-like" not in json.dumps(meter.receipts)


def test_calibration_receipts_cache_and_output_do_not_overwrite(tmp_path):
    client = FakeClient()
    output, cache = tmp_path / "report.json", tmp_path / "cache.json"
    report = run_calibration(ROOT, client, output, cache)
    assert report["status"] == "completed"
    assert report["attempted_requests"] == 3
    assert [len(call["input"]) for call in client.calls] == [64, 28, 10]
    assert report["reported_total_tokens"] == 30
    assert len(report["rankings"]) == 10
    assert len(json.loads(cache.read_text())["document_vectors"]) == 92
    before = output.read_bytes()
    with pytest.raises(ValueError, match="overwrite"):
        run_calibration(ROOT, client, output, cache)
    assert len(client.calls) == 3
    assert output.read_bytes() == before


def test_provider_failure_preserves_safe_receipt_and_stops(tmp_path):
    client = FakeClient(failure=True)
    output = tmp_path / "failed.json"
    report = run_calibration(ROOT, client, output, tmp_path / "cache.json")
    assert report["status"] == "failed"
    assert report["attempted_requests"] == 1
    assert not (tmp_path / "cache.json").exists()
    assert "secret-like" not in output.read_text()


def test_cosine_validates_shape_and_vector_norm():
    assert cosine([1.0, 0.0], [0.0, 1.0]) == 0
    assert cosine([2.0, 0.0], [1.0, 0.0]) == 1
    with pytest.raises(ValueError):
        cosine([1.0], [1.0, 0.0])
    with pytest.raises(ValueError):
        cosine([0.0], [1.0])
