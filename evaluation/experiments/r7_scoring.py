"""Offline evidence scoring; Gold is consumed only after retrieval has finished."""

from math import log2


def score_retrieval(
    hits, evidence, allowed_document_ids, gold_paths=(), returned_paths=()
):
    ids = [hit.chunk_id for hit in hits]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate final candidates")
    units = [set(unit["chunk_ids"]) for unit in evidence]
    matched, gains = set(), []
    first = None
    for rank, cid in enumerate(ids, 1):
        covered = {i for i, unit in enumerate(units) if cid in unit}
        if covered and first is None:
            first = rank
        if rank <= 5:
            gains.append(int(bool(covered - matched)))
            matched.update(covered)
    ideal = sum(1 / log2(i + 2) for i in range(min(5, len(units))))
    paths = {tuple(path) for path in returned_paths}
    expected_paths = [tuple(path["edge_ids"]) for path in gold_paths]
    return {
        "evidence_recall_at_5": len(matched) / len(units) if units else None,
        "mrr": (1 / first if first else 0.0) if units else None,
        "ndcg_at_5": sum(g / log2(i + 2) for i, g in enumerate(gains)) / ideal
        if ideal
        else None,
        "all_candidate_evidence_coverage": sum(bool(set(ids) & unit) for unit in units)
        / len(units)
        if units
        else None,
        "graph_path_correctness": sum(path in paths for path in expected_paths)
        / len(expected_paths)
        if expected_paths
        else None,
        "scope_violations": sum(
            hit.document_id not in allowed_document_ids for hit in hits
        ),
        "unique_candidates": len(ids),
    }


def score_citations(citations, hits, evidence):
    by_id = {hit.chunk_id: hit for hit in hits}
    units = [set(unit["chunk_ids"]) for unit in evidence]
    valid, supports, covered = 0, 0, set()
    for citation in citations:
        hit = by_id.get(citation["chunk_id"])
        correct = hit is not None and (hit.document_id, hit.page_number) == (
            citation["source_id"],
            citation["page_number"],
        )
        valid += correct
        matched = {
            i for i, unit in enumerate(units) if correct and hit.chunk_id in unit
        }
        supports += bool(matched)
        covered.update(matched)
    return {
        "identity_source_page_correct": valid,
        "gold_support_proxy_correct": supports,
        "citation_count": len(citations),
        "evidence_coverage": len(covered) / len(units) if units else None,
    }
