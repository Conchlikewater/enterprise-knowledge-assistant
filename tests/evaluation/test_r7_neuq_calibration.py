from types import SimpleNamespace

import pytest

from evaluation.r7_neuq_calibration import (
    DIMENSIONS,
    MAX_BUDGET_USD,
    MAX_INPUT_TOKEN_UPPER_BOUND,
    MAX_REQUESTS,
    MODEL,
    MeteredClient,
    _rank,
    _validate_approval,
)


class FakeClient:
    def __init__(self, fail=False):
        self.embeddings = self
        self.calls = []
        self.fail = fail

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            raise RuntimeError("private-provider-body")
        return SimpleNamespace(
            model=MODEL,
            usage=SimpleNamespace(prompt_tokens=1, total_tokens=1),
            data=[],
        )


def approval():
    return {
        "status": "approved_by_user",
        "purpose": "development_threshold_calibration_only",
        "candidate_corpus_sha256": "a" * 64,
        "model": MODEL,
        "max_requests": MAX_REQUESTS,
        "max_input_token_upper_bound": MAX_INPUT_TOKEN_UPPER_BOUND,
        "max_budget_usd": MAX_BUDGET_USD,
        "formal_100_question_run": False,
    }


def test_approval_is_exactly_bound_to_scope_and_budget():
    plan = {"candidate_corpus_sha256": "a" * 64}
    _validate_approval(approval(), plan)
    for key, bad in (
        ("purpose", "formal_experiment"),
        ("model", "different-model"),
        ("max_requests", MAX_REQUESTS + 1),
        ("formal_100_question_run", True),
    ):
        changed = {**approval(), key: bad}
        with pytest.raises(ValueError, match="approval"):
            _validate_approval(changed, plan)


def test_meter_blocks_wrong_model_request_count_and_budget():
    client = FakeClient()
    meter = MeteredClient(client, approval())
    with pytest.raises(ValueError, match="approved"):
        meter.create(input=["x"], model="wrong", dimensions=DIMENSIONS)
    with pytest.raises(ValueError, match="approved"):
        meter.create(
            input=["x" * (MAX_INPUT_TOKEN_UPPER_BOUND + 1)],
            model=MODEL,
            dimensions=DIMENSIONS,
        )
    assert not client.calls


def test_failed_provider_attempt_records_only_safe_error_type():
    meter = MeteredClient(FakeClient(fail=True), approval())
    with pytest.raises(RuntimeError, match="private-provider-body"):
        meter.create(input=["test"], model=MODEL, dimensions=DIMENSIONS)
    assert meter.attempt_count == 1
    assert meter.receipts == [
        {
            "request": 1,
            "input_count": 1,
            "status": "failed",
            "error_type": "RuntimeError",
            "latency_ms": meter.receipts[0]["latency_ms"],
        }
    ]
    assert "private-provider-body" not in str(meter.receipts)


def test_calibration_excludes_stronger_out_of_scope_evidence():
    chunks = [
        SimpleNamespace(chunk_id="outside", source_id="blocked", page_number=1),
        SimpleNamespace(chunk_id="inside", source_id="allowed", page_number=1),
    ]
    questions = [
        {"id": "dev-scope", "answerable": False, "allowed_document_ids": ["allowed"]}
    ]
    result = _rank(chunks, questions, {}, [[1.0, 0.0], [0.0, 1.0]], [[1.0, 0.0]])
    assert [item["chunk_id"] for item in result[0]["top5"]] == ["inside"]
    assert result[0]["top5"][0]["matches_gold"] is False
