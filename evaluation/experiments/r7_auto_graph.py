"""Export validated extraction records as a quarantined, source-scoped graph."""

import argparse
import json
from pathlib import Path

from evaluation.experiments.r7_replay import write_new

TYPES = {
    "REQUIRES": "Course",
    "HAS_CREDIT": "Credit",
    "OFFERED_IN": "Semester",
    "BELONGS_TO": "Program",
}


def assemble(records):
    nodes, edges, declarations = {}, {}, []
    failed = 0
    for record in records:
        if record["status"] != "validated_pending_semantic_review":
            failed += 1
            continue
        extraction = record["extraction"]
        declarations.append(
            {
                "document_id": record["document_id"],
                "chunk_id": record["chunk_id"],
                "state": extraction["prerequisite_state"],
            }
        )
        for item in extraction["edges"]:
            if (
                item["document_id"] != record["document_id"]
                or item["chunk_id"] != record["chunk_id"]
            ):
                raise ValueError("Extraction record source mismatch")
            provenance = {
                k: item[k]
                for k in ("document_id", "source_sha256", "chunk_id", "page_number")
            }
            if item["id"] in edges and edges[item["id"]] != item:
                raise ValueError("Conflicting edge identity")
            edges[item["id"]] = item
            for key, kind, label in (
                (item["subject"], "Course", item["document_id"]),
                (item["object"], TYPES[item["predicate"]], item["object_text"]),
            ):
                node = nodes.setdefault(
                    key, {"id": key, "type": kind, "label": label, "provenance": []}
                )
                if node["type"] != kind or node["label"] != label:
                    raise ValueError("Conflicting node identity")
                if provenance not in node["provenance"]:
                    node["provenance"].append(provenance)
    return {
        "schema_version": "r7-auto-property-graph-v1",
        "status": "quarantined_pending_semantic_review",
        "nodes": sorted(nodes.values(), key=lambda n: n["id"]),
        "edges": sorted(edges.values(), key=lambda e: e["id"]),
        "declarations": declarations,
        "failed_chunks_excluded": failed,
        "human_review_coverage": 0,
        "cross_document_entity_resolution": False,
        "production_integration": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary = json.loads((args.run_dir / "summary.json").read_text(encoding="utf-8"))
    records = [
        json.loads(p.read_text(encoding="utf-8"))
        for p in sorted(args.run_dir.glob("chunk_*.json"))
    ]
    if len(records) != summary["planned"]:
        raise ValueError("Incomplete run cannot be exported")
    graph = assemble(records)
    write_new(args.output, graph)
    print(
        json.dumps(
            {
                "nodes": len(graph["nodes"]),
                "edges": len(graph["edges"]),
                "excluded_failed_chunks": graph["failed_chunks_excluded"],
                "status": graph["status"],
            }
        )
    )


if __name__ == "__main__":
    main()
