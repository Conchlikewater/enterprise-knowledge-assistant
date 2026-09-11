"""Text-free result artifacts with explicit provenance and offline rescoring."""

import json
from dataclasses import asdict

from evaluation.experiments.r7_retrieval import Hit
from evaluation.experiments.r7_scoring import score_retrieval


def pack_result(question_id, arm, result):
    # Queries are available to the local runner but are not exported in traces.
    trace = [
        {key: value for key, value in row.items() if key != "query"}
        for row in result["trace"]
    ]
    return {
        "schema_version": "r7-retrieval-trajectory-v1",
        "question_id": question_id,
        "arm": arm,
        "hits": [asdict(hit) for hit in result["hits"]],
        "trace": trace,
        "stop_reason": result["stop_reason"],
        "retrieval_calls": result["retrieval_calls"],
    }


def replay(record, gold, allowed_document_ids):
    if record["schema_version"] != "r7-retrieval-trajectory-v1":
        raise ValueError("Unsupported trajectory")
    if record["question_id"] != gold["question_id"]:
        raise ValueError("Trajectory and Gold identity mismatch")
    hits = [
        Hit(**{**item, "path": tuple(item.get("path", ()))}) for item in record["hits"]
    ]
    return score_retrieval(
        hits,
        gold["evidence"],
        allowed_document_ids,
        gold.get("gold_graph_paths", ()),
        [h.path for h in hits if h.path],
    )


def write_new(path, payload):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
