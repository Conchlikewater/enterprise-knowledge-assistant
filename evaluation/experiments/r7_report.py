"""Join completed trajectories to Gold, never the reverse data flow."""

from statistics import mean

from evaluation.experiments.r7_decision import decide
from evaluation.experiments.r7_paired import confusion, paired_delta, percentile
from evaluation.experiments.r7_replay import replay
from evaluation.experiments.r7_retrieval import Hit
from evaluation.experiments.r7_scoring import score_citations

ARMS = ("dense_top5", "dense_retry_5x2", "graph_dense_retry_5x2")
METRICS = (
    "evidence_recall_at_5",
    "mrr",
    "ndcg_at_5",
    "all_candidate_evidence_coverage",
)


def judge_promotion(report, gates):
    """Missing denominators fail closed; passing never authorizes app integration."""
    graph = report["arms"][ARMS[2]]
    dense = report["arms"][ARMS[1]]
    paired = report["paired"][f"{ARMS[2]}-minus-{ARMS[1]}"]
    relation = paired["relationship_and_multi_hop"]
    ordinary = paired.get("ordinary_fact", {})
    multi = paired.get("multi_hop", {})
    checks = {}

    def minimum(name, value, key):
        checks[name] = value is not None and value >= gates[key]

    minimum(
        "relationship_recall",
        relation["evidence_recall_at_5"]["mean_delta"],
        "relationship_multi_hop_recall_delta_min",
    )
    minimum(
        "relationship_ndcg",
        relation["ndcg_at_5"]["mean_delta"],
        "relationship_multi_hop_ndcg_delta_min",
    )
    minimum(
        "multi_evidence",
        multi.get("all_candidate_evidence_coverage", {}).get("mean_delta"),
        "multi_hop_evidence_coverage_delta_min",
    )
    recalls = relation["evidence_recall_at_5"]
    minimum(
        "relation_wins",
        recalls["wins"] - recalls["losses"],
        "relationship_multi_hop_recall_wins_minus_losses_min",
    )
    facts = ordinary.get("evidence_recall_at_5", {})
    minimum(
        "ordinary_recall", facts.get("mean_delta"), "ordinary_fact_recall_delta_min"
    )
    checks["ordinary_regressions"] = (
        facts.get("paired_n", 0) > 0
        and facts["losses"] <= gates["ordinary_fact_regressed_questions_max"]
    )
    checks["scope"] = (
        sum(r["scope_violations"] for r in graph["rows"])
        <= gates["scope_violations_max"]
    )
    citations = sum(r["citations"]["citation_count"] for r in graph["rows"])
    correct = sum(r["citations"]["identity_source_page_correct"] for r in graph["rows"])
    minimum(
        "citation_identity",
        correct / citations if citations else None,
        "citation_identity_source_page_min",
    )
    a, b = graph["answer_refuse"]["accuracy"], dense["answer_refuse"]["accuracy"]
    minimum(
        "answer_refuse",
        a - b if a is not None and b is not None else None,
        "answer_refuse_delta_min",
    )
    paths = [
        r["graph_path_correctness"]
        for r in graph["rows"]
        if r["graph_path_correctness"] is not None
    ]
    minimum("graph_path", mean(paths) if paths else None, "graph_path_correctness_min")
    a, b = graph["p95_cached_retrieval_ms"], dense["p95_cached_retrieval_ms"]
    checks["cached_latency"] = (
        a is not None
        and b is not None
        and b > 0
        and a / b <= gates["p95_latency_ratio_max"]
    )
    return {
        "checks": checks,
        "all_passed": all(checks.values()),
        "verdict": "eligible_for_separate_review"
        if all(checks.values())
        else "negative_or_inconclusive",
        "production_integration_authorized": False,
    }


def build_report(records, gold_questions, scopes, *, resamples=10000):
    gold = {q["question_id"]: q for q in gold_questions}
    if len(gold) != len(gold_questions) or gold.keys() != scopes.keys():
        raise ValueError("Gold/scope question mismatch")
    indexed = {(row["arm"], row["question_id"]): row for row in records}
    if len(indexed) != len(records) or set(indexed) != {
        (a, q) for a in ARMS for q in gold
    }:
        raise ValueError("Incomplete or duplicate three-arm trajectories")
    by_arm = {}
    for arm in ARMS:
        rows = []
        for qid in sorted(gold):
            record, label = indexed[arm, qid], gold[qid]
            hits = [
                Hit(**{**h, "path": tuple(h.get("path", ()))}) for h in record["hits"]
            ]
            if (
                record["retrieval_calls"] != len(record["trace"])
                or not 1 <= record["retrieval_calls"] <= (1 if arm == ARMS[0] else 2)
                or len(hits) > (5 if arm == ARMS[0] else 10)
            ):
                raise ValueError("Trajectory budget mismatch")
            decision = decide(hits, scopes[qid])
            metrics = replay(record, label, scopes[qid])
            citations = score_citations(decision["citations"], hits, label["evidence"])
            rows.append(
                {
                    "question_id": qid,
                    "category": label["category"],
                    **metrics,
                    "behavior": decision["behavior"],
                    "expected_behavior": label["expected_behavior"],
                    "citations": citations,
                    "latency_ms": sum(t["latency_ms"] for t in record["trace"]),
                    "retrieval_calls": record["retrieval_calls"],
                    "prefusion_candidates": sum(
                        t["prefusion_candidates"] for t in record["trace"]
                    ),
                }
            )
        summary = {}
        for metric in METRICS:
            values = [row[metric] for row in rows if row[metric] is not None]
            summary[metric] = {
                "mean": mean(values) if values else None,
                "n": len(values),
            }
        by_arm[arm] = {
            "rows": rows,
            "metrics": summary,
            "answer_refuse": confusion(rows),
            "p50_cached_retrieval_ms": percentile([r["latency_ms"] for r in rows], 0.5),
            "p95_cached_retrieval_ms": percentile(
                [r["latency_ms"] for r in rows], 0.95
            ),
        }
    comparisons = {}
    categories = {q["category"] for q in gold_questions}
    for base, candidate in ((ARMS[0], ARMS[1]), (ARMS[0], ARMS[2]), (ARMS[1], ARMS[2])):
        comparison = {}
        for group in ["all", *sorted(categories), "relationship_and_multi_hop"]:
            selected = (
                None
                if group == "all"
                else (
                    {"relationship", "multi_hop"}
                    if group == "relationship_and_multi_hop"
                    else {group}
                )
            )
            comparison[group] = {
                metric: paired_delta(
                    by_arm[base]["rows"],
                    by_arm[candidate]["rows"],
                    metric,
                    categories=selected,
                    resamples=resamples,
                )
                for metric in METRICS
            }
        comparisons[f"{candidate}-minus-{base}"] = comparison
    return {
        "arms": by_arm,
        "paired": comparisons,
        "question_count": len(gold),
        "latency_scope": "cached local retrieval only; embedding request latency must be reported separately",
        "answer_scope": "evidence availability only, not LLM factual answer quality",
        "production_promotion_authorized": False,
    }
