# Portfolio Release Checklist

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
- [x] deterministic 10-document / 20-question evaluation

## Test Evidence

- [x] unit, integration, and evaluation suites pass with warnings as errors
- [x] dependency consistency check passes
- [x] Ruff lint and format checks pass
- [x] branch coverage remains above the enforced 85% floor
- [x] application and test modules compile
- [x] tracked evaluation report matches a fresh evaluator run
- [x] synthetic live OpenAI upload-to-delete flow has passed
- [x] corpus and report regenerate byte-for-byte

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

The standalone repository target was selected by the owner. While this project
still lives inside a larger local Git repository, GitHub will discover the
tracked workflow after this directory becomes the root of its own repository.
