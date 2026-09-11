"""Hash-checked local assembly; graph building never receives question Gold."""

import hashlib
import json
from pathlib import Path

from evaluation.experiments.r7_retrieval import CachedDense, Hit, PropertyGraph
from evaluation.r7_chunk_profile_analysis import (
    PREFERRED_PROFILE,
    PROFILE_CANDIDATES,
    _admitted_inputs,
)
from evaluation.r7_corpus_contract import build_complete_corpus


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def bind_assertions(relations, chunks):
    """Bind every source assertion, without reading expected paths or answers."""
    bindings = []
    for edge in relations["edges"]:
        kind = (
            "prerequisites" if edge["predicate"] == "REQUIRES" else "course_information"
        )
        candidates = [
            chunk
            for chunk in chunks
            if (chunk.source_id, chunk.page_number, chunk.kind)
            == (edge["source_id"], edge["page_number"], kind)
        ]
        if len(candidates) != 1:
            raise ValueError("Assertion requires one unambiguous source chunk")
        chunk = candidates[0]
        if edge.get("source_sha256") not in (None, chunk.source_sha256):
            raise ValueError("Assertion source hash mismatch")
        bindings.append(
            {
                "assertion_id": edge["id"],
                "source_id": chunk.source_id,
                "page_number": chunk.page_number,
                "chunk_id": chunk.chunk_id,
            }
        )
    return bindings


def load_local(root, candidate_path, cache_path):
    root = Path(root)
    r7 = root / "evaluation/r7"
    protocol = read_json(r7 / "neuq_2023_protocol.json")
    if not protocol["phase_gate"]["r7c_graph_code_allowed"]:
        raise ValueError("R7-C gate is closed")
    for asset in protocol["frozen_assets"].values():
        if sha256(root / asset["path"]) != asset["file_sha256"]:
            raise ValueError("Frozen asset hash mismatch")
    admission = read_json(
        root / protocol["frozen_assets"]["safe_corpus_admission"]["path"]
    )
    args = _admitted_inputs(read_json(candidate_path), admission)
    chunks = build_complete_corpus(
        args[0], args[1], args[2], PROFILE_CANDIDATES[PREFERRED_PROFILE], args[3]
    )
    calibration = read_json(
        root / protocol["frozen_assets"]["development_calibration"]["path"]
    )
    raw_report_path = root / calibration["raw_local_report"]
    if sha256(raw_report_path) != calibration["raw_report_file_sha256"]:
        raise ValueError("Calibration receipt hash mismatch")
    if sha256(cache_path) != read_json(raw_report_path)["vector_cache_sha256"]:
        raise ValueError("Vector cache hash mismatch")
    cache = read_json(cache_path)
    if (
        cache["chunk_ids"] != [chunk.chunk_id for chunk in chunks]
        or cache["candidate_corpus_sha256"]
        != admission["output_sha256"]["candidate_corpus"]
    ):
        raise ValueError("Cache and corpus differ")
    development = read_json(
        root / protocol["frozen_assets"]["development_questions"]["path"]
    )["questions"]
    if cache["question_ids"] != [q["id"] for q in development]:
        raise ValueError("Development cache order mismatch")
    query_vectors = dict(
        zip((q["question"] for q in development), cache["query_vectors"], strict=True)
    )
    hits = [Hit(c.chunk_id, c.source_id, c.page_number, 0) for c in chunks]
    relations = read_json(root / protocol["frozen_assets"]["relations"]["path"])
    bindings = bind_assertions(relations, chunks)
    graph = PropertyGraph(
        relations["nodes"], relations["edges"], bindings, {h.chunk_id: h for h in hits}
    )
    dense = CachedDense(hits, cache["document_vectors"], query_vectors)
    return protocol, chunks, development, dense, graph
