# RAG V1 Scope and Acceptance

- Product: Enterprise Knowledge Assistant
- Version: 0.1.0
- Runtime: Python 3.12, FastAPI, SQLite, local Qdrant, OpenAI API
- Scope status: V1 implemented; V2 evaluation and portfolio audit frozen

## Goal

Build a small local knowledge-base API that ingests documents, retrieves
document-scoped evidence, generates grounded answers, and returns citations
whose metadata comes from stored chunks rather than the language model.

## Final V1 Scope

- UTF-8 TXT and text-based PDF upload
- synchronous validation, storage, parsing, chunking, embedding, and indexing
- SQLite document records and persistent local Qdrant vectors
- one OpenAI embedding provider and one OpenAI LLM provider
- explicit one-or-more-document retrieval scope
- optional score threshold and configurable Top-K
- evidence-only answer generation
- application-built citations with filename, page, chunk, excerpt, and score
- document listing, lookup, and consistent deletion from all stores
- typed configuration, stable errors, request IDs, and privacy-safe logs
- unit, integration, security-oriented, and offline evaluation tests

## Acceptance Evidence

| Requirement | Evidence | Status |
|---|---|---|
| Ingest at least five documents | Offline evaluation ingests 10 tracked fixtures | Passed |
| Support TXT and PDF | 6 TXT and 4 PDF fixtures, including two multi-page PDFs | Passed |
| Produce searchable non-empty chunks | Domain invariants and evaluation gate | Passed |
| Retrieve only selected documents | Service/API tests and four isolation questions | Passed |
| Generate evidence-grounded answers | Answer service/API tests and live synthetic smoke check | Passed |
| Return traceable citations | Citation unit/API tests and evaluation integrity gate | Passed |
| Handle unanswerable questions | Eight evaluation questions require no-evidence behavior | Passed |
| Delete files, records, and vectors | Unit, API, and evaluation deletion checks | Passed |
| Expose the workflow through FastAPI | Seven operations across five OpenAPI paths | Passed |
| Use stable privacy-safe errors and logs | Exception, API, and log-content tests | Passed |
| Evaluate 50 typed questions | Tracked deterministic report and category metrics | Passed |

The current evaluation report is `evaluation/latest_report.json`. The release
checklist records the final installation and repository checks separately.

## Explicitly Out of Scope

- Docker or container orchestration
- Celery, RabbitMQ, Redis, or background ingestion jobs
- authentication, authorization, multi-tenancy, or public deployment
- OCR, scanned PDFs, Markdown, DOCX, spreadsheets, or presentations
- several active model or vector-store providers
- production reranking or hybrid search, fine-tuning, agents, tools, MCP, or frontend UI
- large-scale or highly available production storage

Deferred features should be added only after a measured limitation justifies
their cost and the security boundary is redesigned for shared deployment.

The V2 evaluation directory contains a dependency-light BM25/RRF prototype,
but it is not connected to the production API. A same-corpus semantic comparison
showed lower Recall@5 and MRR than Dense retrieval, so the prototype was rejected
rather than promoted.
