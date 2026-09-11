"""A deliberately weak, label-independent evidence availability baseline.

An `answer` outcome means offer retrieved evidence, not assert a factual answer.
This experiment has no answer-generating LLM and cannot verify entailment here.
"""


def decide(hits, allowed_document_ids):
    if any(hit.document_id not in allowed_document_ids for hit in hits):
        raise ValueError("Evidence outside allowed scope")
    unique = {hit.chunk_id: hit for hit in hits}
    if len(unique) < 2:
        return {
            "behavior": "refuse",
            "reason": "fewer_than_two_candidates",
            "citations": [],
        }
    # RRF scores are not cosine scores: do not apply the cosine threshold again.
    return {
        "behavior": "answer",
        "reason": "evidence_available_not_semantic_entailment",
        "citations": [
            {
                "chunk_id": hit.chunk_id,
                "source_id": hit.document_id,
                "page_number": hit.page_number,
            }
            for hit in list(unique.values())[:5]
        ],
    }
