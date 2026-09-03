# V2 Portfolio Release Checklist

This checklist separates implemented functionality from final release proof.
An item is complete only when its evidence was observed in the current worktree.

## Functional Closure

- [x] TXT and text-PDF synchronous ingestion
- [x] safe file validation and compensating rollback
- [x] SQLite document lifecycle
- [x] persistent local Qdrant storage
- [x] document-scoped retrieval
- [x] OpenAI embedding and grounded-answer adapters
- [x] application-built structured citations
- [x] stable error contract and privacy-safe event fields
- [x] deterministic 10-document / 50-question evaluation
- [x] typed evidence contracts with category-level Hit@K, Recall@K, and MRR
- [x] isolated chunk-size, overlap, and Top-K experiments
- [x] opt-in real semantic embedding comparison on synthetic data only
- [x] refusal-threshold sweep without extra provider calls
- [x] BM25/RRF Hybrid prototype evaluated and rejected after measured regression
- [x] structured bad-case catalogue with failure-stage ownership
- [x] local retrieval and answer-orchestration P50/P95 benchmark

## Test Evidence

- [x] unit, integration, and evaluation suites pass with warnings as errors
- [x] dependency consistency check passes
- [x] Ruff lint and format checks pass
- [x] branch coverage remains above the enforced 85% floor
- [x] application and test modules compile
- [x] tracked evaluation report matches a fresh evaluator run
- [x] synthetic live OpenAI upload-to-delete flow has passed
- [x] corpus and report regenerate byte-for-byte
- [x] 152 automated tests pass
- [x] branch-aware total coverage remains 88.29% with an enforced 85% floor
- [x] semantic Dense records 100% Recall@5 and 0.9833 MRR on the synthetic set
- [x] semantic Hybrid regression is tracked rather than hidden

## Release Documentation

- [x] architecture and open-source research decisions are recorded
- [x] provider selection and privacy behavior are recorded
- [x] README contains setup, run, demo, API, configuration, and limitations
- [x] local-only security boundary is explicit
- [x] clean temporary environment installation is re-verified
- [x] real Uvicorn process startup and HTTP readiness are re-verified
- [x] final tracked-file secret and runtime-data audit is complete
- [x] MIT license is selected by the owner
- [x] standalone-repository GitHub Actions workflow is tracked
- [x] V2 release decision and claim boundaries are documented
- [x] create and publish the standalone GitHub repository

The maintained local project now lives in its own Git repository at
`D:\AI_Internship_2026\projects\enterprise-knowledge-assistant`. Its standalone
history is published as `Conchlikewater/enterprise-knowledge-assistant`.
GitHub recognizes `main` as the default branch and the MIT license from the
repository root.
