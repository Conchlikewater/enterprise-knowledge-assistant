# RAG V2 Evaluation Release

- Release state: frozen locally on 2026-08-10
- Product API: V1 modular FastAPI application, version `0.1.0`
- V2 scope: evaluation, retrieval experiments, observability, and portfolio evidence
- Production retrieval decision: OpenAI semantic Dense through local Qdrant
- Publication state: published at
  `https://github.com/2932451552-beep/enterprise-knowledge-assistant`

## What V2 Adds

V2 keeps the application boundary small and adds evidence around its behavior:

- 50 typed questions across eight categories
- exact evidence-level matching rather than filename-only success
- Hit Rate@K, Recall@K, MRR, category metrics, and structured bad cases
- five isolated chunk/overlap/Top-K profiles
- opt-in semantic embedding evaluation on synthetic data only
- refusal-threshold replay without additional API calls
- BM25 and RRF Hybrid prototype using the exact chunks stored in Qdrant
- same-provider Dense-versus-Hybrid comparison
- local retrieval and answer-orchestration P50/P95 benchmark

## Final Evidence

| Evidence | Result |
|---|---:|
| Documents | 10 synthetic fixtures: 6 TXT, 4 PDF, 2 multi-page |
| Questions | 50 typed contracts across 8 categories |
| Tests | 143 passed plus 34 subtests |
| Branch coverage | 88.20% with 85% enforced floor |
| Hashing Recall@5 / MRR | 82.50% / 0.7937 |
| Semantic Dense Recall@5 / MRR | 100% / 0.9833 |
| Semantic Hybrid Recall@5 / MRR | 92.50% / 0.8438 |
| Hybrid answerable regressions | 3 |
| Local retrieval P50 / P95 | 7.6400 / 7.9261 ms |
| Local answer orchestration P50 / P95 | 7.6006 / 7.9745 ms |

The semantic scores describe the tracked synthetic set, not production accuracy.
The latency numbers describe one local Windows machine using hashing embeddings,
temporary local stores, and a deterministic LLM test double. They exclude OpenAI
network latency, concurrency, large documents, and server load.

## Decisions

1. Keep semantic Dense retrieval. It retrieves all annotated evidence on the
   current set and has the best MRR.
2. Reject equal-weight BM25/RRF. It pushes three Dense-recovered evidence chunks
   outside Top-5 and worsens both Recall and MRR.
3. Do not silently promote the `0.37–0.41` threshold interval. It is a useful
   synthetic candidate, not a production guarantee.
4. Keep the two ambiguity cases. Returning several candidates or a clarification
   request remains a visible next product step.
5. Preserve V1 boundaries. No Agent, MCP, OCR, authentication, multi-tenancy,
   background queue, frontend, or public deployment is claimed.

## Reproduce Locally

The complete offline gate does not require an API key:

```powershell
.\.venv\Scripts\python.exe scripts\check_quality.py
.\.venv\Scripts\python.exe scripts\run_evaluation_experiments.py
.\.venv\Scripts\python.exe scripts\run_hybrid_evaluation.py
.\.venv\Scripts\python.exe scripts\run_latency_benchmark.py
.\.venv\Scripts\python.exe scripts\build_bad_case_report.py
```

The semantic experiments are opt-in, send only tracked synthetic text, and incur
a small embedding charge:

```powershell
.\.venv\Scripts\python.exe scripts\run_semantic_evaluation.py --confirm-online
.\.venv\Scripts\python.exe scripts\run_semantic_hybrid_evaluation.py --confirm-online
```

## Portfolio Claim Boundary

Safe claims:

- built and tested a modular local RAG backend with traceable citations
- designed a 50-question typed evaluation and evidence-level retrieval metrics
- improved the hashing baseline by evaluating a real semantic embedding model
- tested Hybrid retrieval and rejected it after a measured regression
- maintained 88.20% branch coverage and a complete local quality gate

Claims that are not supported:

- production or enterprise deployment readiness
- 100% real-world answer accuracy
- online latency below 8 ms
- a production Hybrid or reranking system
- model training, fine-tuning, Agent, or multi-tenant capabilities

## Publication

The working copy remains a subdirectory of the larger `ai-internship-prep`
repository. Its filtered project history is published independently at
`https://github.com/2932451552-beep/enterprise-knowledge-assistant`, without
the parent repository's unrelated projects or local runtime data.
