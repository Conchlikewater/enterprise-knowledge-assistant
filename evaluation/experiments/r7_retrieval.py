"""Bounded experiment-only retrieval; no labels, expected answers or model calls."""

from dataclasses import dataclass
from math import isfinite
from time import perf_counter

from app.services.evidence_sufficiency import EvidenceSufficiencyPolicy
from app.services.query_rewriter import RuleBasedQueryRewriter
from evaluation.r7_calibration import cosine


@dataclass(frozen=True)
class Hit:
    chunk_id: str
    document_id: str
    page_number: int
    score: float
    path: tuple[str, ...] = ()


class CachedDense:
    """Use one shared vector cache; never silently obtain missing embeddings."""

    def __init__(self, chunks, vectors, query_vectors):
        if len(chunks) != len(vectors) or not chunks:
            raise ValueError("Vector count mismatch")
        if len({chunk.chunk_id for chunk in chunks}) != len(chunks):
            raise ValueError("Duplicate chunk")
        dimensions = len(vectors[0])
        for vector in [*vectors, *query_vectors.values()]:
            if (
                not dimensions
                or len(vector) != dimensions
                or any(not isfinite(value) for value in vector)
                or not any(value != 0 for value in vector)
            ):
                raise ValueError("Invalid cached vector")
        self.chunks = tuple(chunks)
        self.vectors = tuple(vectors)
        self.query_vectors = query_vectors

    def __call__(self, query, allowed):
        if query not in self.query_vectors:
            raise ValueError("Query embedding absent from approved cache")
        vector = self.query_vectors[query]
        results = [
            Hit(
                chunk.chunk_id,
                chunk.document_id,
                chunk.page_number,
                cosine(vector, embedding),
            )
            for chunk, embedding in zip(self.chunks, self.vectors, strict=True)
            if chunk.document_id in allowed
        ]
        return sorted(results, key=lambda h: (-h.score, h.chunk_id))[:5]


class PropertyGraph:
    """Source-scoped identities; undirected traversal retains directed assertions."""

    def __init__(self, nodes, edges, bindings, chunks):
        self.nodes = {node["key"]: node for node in nodes}
        if len(self.nodes) != len(nodes):
            raise ValueError("Duplicate graph identity")
        self.adjacency = {key: [] for key in self.nodes}
        self.edges = {}
        by_id = {item["assertion_id"]: item for item in bindings}
        for edge in edges:
            eid = edge["id"]
            if eid in self.edges or edge["predicate"] not in {
                "REQUIRES",
                "BELONGS_TO",
                "OFFERED_IN",
                "HAS_CREDIT",
            }:
                raise ValueError("Invalid assertion")
            binding = by_id[eid]
            chunk = chunks[binding["chunk_id"]]
            if (
                binding["source_id"] != edge["source_id"]
                or binding["page_number"] != edge["page_number"]
                or chunk.document_id != binding["source_id"]
                or chunk.page_number != binding["page_number"]
            ):
                raise ValueError("Assertion provenance mismatch")
            self.edges[eid] = (edge, chunk)
            for key in {edge["subject"], edge["object"]}:
                self.adjacency[key].append(eid)

    def search(self, query, allowed):
        cues = {
            "REQUIRES": ("先修", "prerequisite"),
            "BELONGS_TO": ("专业", "program"),
            "OFFERED_IN": ("学期", "semester"),
            "HAS_CREDIT": ("学分", "credit"),
        }
        text = query.casefold()
        seeds = {
            key
            for key, node in self.nodes.items()
            if any(
                str(node.get(field) or "").casefold() in text
                for field in ("course_name", "course_code", "name")
                if node.get(field)
            )
        }
        candidates = []

        def visit(key, path, visited):
            if len(path) == 3:
                return
            for eid in sorted(self.adjacency[key]):
                edge, chunk = self.edges[eid]
                other = edge["object"] if key == edge["subject"] else edge["subject"]
                if chunk.document_id not in allowed or eid in path or other in visited:
                    continue
                current = (*path, eid)
                exact = sum(node in seeds for node in (edge["subject"], edge["object"]))
                cue = any(word in text for word in cues[edge["predicate"]])
                candidates.append(
                    (
                        (-exact, -int(cue), len(current), current),
                        Hit(
                            chunk.chunk_id,
                            chunk.document_id,
                            chunk.page_number,
                            0.0,
                            current,
                        ),
                    )
                )
                visit(other, current, visited | {other})

        for seed in sorted(seeds):
            visit(seed, (), {seed})
        ordered = [hit for _, hit in sorted(candidates, key=lambda pair: pair[0])]
        return unique(ordered, 5)


def unique(hits, limit):
    result, seen = [], set()
    for hit in hits:
        if hit.chunk_id not in seen:
            result.append(hit)
            seen.add(hit.chunk_id)
        if len(result) == limit:
            break
    return result


def fuse(dense, graph):
    scores, hits = {}, {}
    dense_scores = {hit.chunk_id: hit.score for hit in dense}
    paths = {hit.chunk_id: hit.path for hit in graph}
    for ranking in (dense, graph):
        for rank, hit in enumerate(ranking, 1):
            scores[hit.chunk_id] = scores.get(hit.chunk_id, 0.0) + 1 / (60 + rank)
            hits.setdefault(hit.chunk_id, hit)
    ordered = sorted(
        hits,
        key=lambda cid: (
            -scores[cid],
            -dense_scores.get(cid, float("-inf")),
            len(paths.get(cid, ())) if cid in paths else float("inf"),
            cid,
        ),
    )
    return [
        Hit(
            cid,
            hits[cid].document_id,
            hits[cid].page_number,
            scores[cid],
            paths.get(cid, ()),
        )
        for cid in ordered[:5]
    ]


def run_arm(query, document_ids, arm, dense_search, graph=None, threshold=0.53):
    """Injected Dense search returns scored Hits; exceptions never cause retries."""
    if arm not in {"dense_top5", "dense_retry_5x2", "graph_dense_retry_5x2"}:
        raise ValueError("Unknown arm")
    if arm == "graph_dense_retry_5x2" and graph is None:
        raise ValueError("Graph arm requires graph")
    allowed = frozenset(document_ids)
    trace, final = [], []
    current = query
    stop = "single_round"
    for round_number in range(1, (1 if arm == "dense_top5" else 2) + 1):
        started = perf_counter()
        raw = dense_search(current, allowed)
        if any(
            hit.document_id not in allowed or not isfinite(hit.score) for hit in raw
        ):
            raise ValueError("Dense scope or score violation")
        dense = unique(
            sorted(
                (h for h in raw if h.score >= threshold),
                key=lambda h: (-h.score, h.chunk_id),
            ),
            5,
        )
        assessment = EvidenceSufficiencyPolicy().assess(
            dense, top_k=5, score_threshold=threshold
        )
        graph_hits = (
            graph.search(current, allowed) if arm == "graph_dense_retry_5x2" else []
        )
        if any(hit.document_id not in allowed for hit in graph_hits):
            raise ValueError("Graph scope violation")
        selected = fuse(dense, graph_hits) if graph_hits else dense
        before = len(final)
        final = unique([*final, *selected], 10)
        trace.append(
            {
                "round": round_number,
                "query": current,
                "dense_chunk_ids": [h.chunk_id for h in dense],
                "graph_chunk_ids": [h.chunk_id for h in graph_hits],
                "graph_paths": [list(h.path) for h in graph_hits],
                "prefusion_candidates": len(dense) + len(graph_hits),
                "selected_chunk_ids": [h.chunk_id for h in selected],
                "new_unique_candidates": len(final) - before,
                "dense_should_retry": assessment.should_retry,
                "latency_ms": (perf_counter() - started) * 1000,
            }
        )
        if arm == "dense_top5":
            break
        if not assessment.should_retry:
            stop = "dense_sufficient"
            break
        if round_number == 2:
            stop = "round_limit"
            break
        rewritten = RuleBasedQueryRewriter().rewrite(current)
        if rewritten is None:
            stop = "no_distinct_rewrite"
            break
        current = rewritten
    return {
        "hits": final,
        "trace": trace,
        "stop_reason": stop,
        "retrieval_calls": len(trace),
        "unique_candidates": len(final),
    }
