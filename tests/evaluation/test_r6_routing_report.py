from __future__ import annotations

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load(relative_path: str) -> dict:
    return json.loads((PROJECT_ROOT / relative_path).read_text(encoding="utf-8"))


def test_r6_report_is_bound_to_the_frozen_assets() -> None:
    protocol = _load("evaluation/r6_routing_protocol.json")
    report = _load("evaluation/r6_routing_report.json")
    assets = protocol["frozen_evaluation_assets"]

    assert report["protocol"]["version"] == protocol["protocol_version"]
    assert report["frozen_assets"] == {
        "route_dataset": assets["route_dataset"],
        "route_dataset_sha256": assets["route_dataset_sha256"],
        "retry_dataset": assets["retry_dataset"],
        "retry_dataset_sha256": assets["retry_dataset_sha256"],
    }
    assert len(report["implementation_commit"]) == 40


def test_r6_report_passes_every_preregistered_gate() -> None:
    report = _load("evaluation/r6_routing_report.json")

    assert report["passed"] is True
    assert report["failed_checks"] == []
    assert all(report["acceptance"]["checks"].values())
    assert report["routing"]["sample_count"] == 36
    assert report["routing"]["correct_count"] == 36
    assert report["routing"]["business_fact_direct_answer_violation_count"] == 0
    assert report["retry"]["case_count"] == 12
    assert report["retry"]["correct_count"] == 12
    assert report["constraints"]["retrieval_call_limit_breach_count"] == 0
    assert report["constraints"]["document_scope_violation_count"] == 0


def test_r6_report_records_offline_cost_and_scope_limitations() -> None:
    report = _load("evaluation/r6_routing_report.json")
    execution = report["execution"]
    limitations = " ".join(report["limitations"]).casefold()

    assert execution["provider"] == "none"
    assert execution["network_calls"] == 0
    assert execution["embedding_calls"] == 0
    assert execution["llm_calls"] == 0
    assert execution["router_token_count"] == 0
    assert execution["router_estimated_cost_usd"] == 0.0
    assert "hand-authored" in limitations
    assert "not open-domain" in limitations
    assert "does not authorize or start r7" in limitations
