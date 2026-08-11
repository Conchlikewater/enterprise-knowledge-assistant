# Enterprise Knowledge Assistant Architecture Decision Log

- Project: Enterprise Knowledge Assistant
- Decision date: 2026-08-02
- Status: V1 architecture approved for implementation planning
- Main reference: `danny-avila/rag_api`
- Secondary reference: `zylon-ai/private-gpt`
- Enterprise boundary reference: `infiniflow/ragflow`
- Educational reference: `bakrianoo/mini-rag`

---

## 1. Purpose

This document records the architecture decisions for the first version of the Enterprise Knowledge Assistant.

Its goals are to:

- explain the selected V1 architecture
- identify which open-source patterns will be adopted
- record which patterns will be rejected or deferred
- define module boundaries
- define the ingestion and retrieval flows
- define document and chunk metadata
- define citation behavior
- define error and logging policies
- establish the minimum testing and evaluation requirements

The project will learn from public repositories without copying their full implementations.

---

## 2. Research Evidence

Four repositories received Level A reviews.

| Repository | Role in the Decision |
|---|---|
| `danny-avila/rag_api` | Main architecture reference |
| `zylon-ai/private-gpt` | Secondary reference for service boundaries, metadata, and citations |
| `infiniflow/ragflow` | Enterprise complexity boundary |
| `bakrianoo/mini-rag` | Educational pipeline and implementation counterexample |

No repository was run locally because the required environments were not practical:

- Docker is unavailable.
- Python 3.10 and Python 3.11 are unavailable.
- The installed Python version is 3.12.
- Ollama is unavailable.
- Several repositories require databases, workers, model servers, or external credentials.

Static analysis of source code, configuration, tests, routes, and documented workflows provided enough evidence for the architecture decisions.

---

## 3. Repository 1 Review Correction

The earlier quick-review record identified `12a4469` as the latest observed commit.

The Level C review found a newer current commit:

- Correct reviewed commit: `4985b37`
- Commit date: 2026-07-31
- Commit purpose: safe parallel ingestion consumers and rollback improvements

The newer version also contains recent database-startup safeguards and dependency updates.

All Level C conclusions in this document refer to commit `4985b37`.

---

## 4. Level C Analysis of danny-avila/rag_api

### 4.1 Actual Responsibility

The repository is an ID-based document indexing and retrieval API.

Its main responsibilities are:

- receive uploaded or locally available documents
- select a document loader
- split document content into chunks
- generate embeddings
- store chunks and vectors
- associate chunks with `file_id` and `user_id`
- retrieve chunks from one or more selected files
- reconstruct document context
- delete indexed documents
- expose health and diagnostic endpoints

It does not implement a complete answer-generation service. An external application is expected to use the retrieved chunks when constructing an LLM response.

This limited responsibility is the main reason it remains the closest reference for our V1.

### 4.2 Current Module Structure

```text
rag_api/
├── main.py
├── app/
│   ├── config.py
│   ├── constants.py
│   ├── middleware.py
│   ├── models.py
│   ├── routes/
│   │   ├── document_routes.py
│   │   └── pgvector_routes.py
│   ├── services/
│   │   ├── database.py
│   │   ├── mongo_client.py
│   │   └── vector_store/
│   │       ├── factory.py
│   │       ├── async_pg_vector.py
│   │       ├── extended_pg_vector.py
│   │       └── atlas_mongo_vector.py
│   └── utils/
│       ├── document_loader.py
│       └── health.py
├── tests/
├── requirements.txt
└── docker-compose.yaml
```

### 4.3 Startup and Shutdown Flow

The application uses a FastAPI lifespan function.

At startup it:

1. creates a bounded thread pool
2. initializes the PostgreSQL connection pool when PGVector is selected
3. performs optional database index and metadata migrations
4. registers middleware and routers

At shutdown it:

1. closes the async PostgreSQL pool
2. waits for thread-pool work to finish
3. closes vector-store connections
4. disposes database engines where possible

This lifecycle pattern is worth adopting.

However, the repository also creates its embedding client and vector store while importing `app.config`. That introduces import-time side effects and makes configuration and testing harder.

Our V1 will create providers during application startup instead.

### 4.4 Ingestion Flow

The reviewed upload flow is:

```text
HTTP upload
    ↓
validate and create unique temporary path
    ↓
save upload in small blocks
    ↓
select loader using extension and content type
    ↓
load document outside the event loop
    ↓
split document into overlapping chunks
    ↓
add file, user, digest, page, and source metadata
    ↓
generate embeddings
    ↓
insert chunks into the vector store
    ↓
return document result
    ↓
delete temporary file
```

For large files, the repository can use a bounded producer-consumer pipeline.

The pipeline:

- divides chunks into batches
- limits the in-memory queue
- runs several consumers
- tracks an ingestion-attempt identifier
- stops peer consumers when one fails
- waits for in-flight inserts
- removes vectors created by the failed attempt
- preserves source chunk order

This is a strong production pattern, but it is too complex for V1.

Our V1 will adopt the rollback concept while using sequential ingestion.

### 4.5 Document Metadata

Repository 1 stores metadata such as:

- `file_id`
- `user_id`
- content digest
- source path
- page number
- ingestion attempt identifier
- ingestion start time
- source chunk index

The design correctly preserves loader metadata while adding application metadata.

The V1 will adopt explicit document and chunk metadata but will use clearer names:

- `document_id` instead of `file_id`
- `chunk_id`
- `chunk_index`
- `filename`
- `page_number`
- `content_hash`

Local filesystem paths will not be returned as source citations.

### 4.6 Retrieval Flow

The reviewed retrieval flow is:

```text
query text
    ↓
query embedding
    ↓
vector similarity search
    ↓
file_id metadata filter
    ↓
optional distance threshold
    ↓
basic ownership check
    ↓
return matching chunks and scores
```

The API supports both:

- retrieval from one file
- retrieval from several selected files

File-scoped filtering is the most important pattern adopted from this repository.

The V1 will call this document-scoped retrieval and will accept a list of `document_id` values.

### 4.7 Document Context Reconstruction

The repository can load all chunks belonging to a file and restore their original order.

The current version uses:

- ingestion-attempt identifiers
- attempt start times
- source chunk indexes
- overlap-aware text reconstruction
- page headings

This is useful for retrieving complete document context.

The V1 does not need complete-context reconstruction initially. It will preserve `chunk_index` and `page_number` so this feature can be added later.

### 4.8 Vector-Store Boundary

Repository 1 places PGVector and Atlas MongoDB behind a factory.

This is useful because routes do not need to know every connection detail.

However, route code still performs concrete type checks such as checking whether the store is `AsyncPgVector`. This leaks infrastructure decisions into the API layer.

The V1 will define one vector-store interface. API routers and services will not check concrete provider classes.

### 4.9 Async Behavior

The repository wraps blocking LangChain vector-store operations in a thread pool.

This keeps blocking work away from the FastAPI event loop but is not equivalent to using a fully asynchronous vector driver.

The approach is pragmatic, but the custom executor and parallel consumer system add complexity.

The V1 will:

- provide synchronous request semantics
- keep blocking parsing and model operations outside the event loop
- process one document sequentially
- avoid a custom parallel ingestion pipeline

### 4.10 Error Handling Findings

Positive patterns:

- FastAPI validation errors receive a structured response.
- Path traversal attempts are rejected.
- Missing documents can return 404.
- temporary files are cleaned in `finally` blocks
- ingestion failures are logged
- recent batch ingestion can perform compensating rollback

Patterns that must not be copied:

- internal exception text is sometimes returned directly to clients
- several unexpected failures are converted to 400 responses
- some functions return error dictionaries instead of raising typed exceptions
- health failure branches return tuple-shaped values instead of an explicit response status
- document deletion occurs before all requested identifiers are confirmed to exist
- different routes use inconsistent response structures

The V1 will use typed application exceptions and one global error handler.

### 4.11 Security Findings

Positive patterns:

- filenames receive unique temporary paths
- resolved paths must stay within the configured upload directory
- temporary uploads are cleaned
- JWT verification can be enabled
- path-traversal behavior has dedicated tests

Patterns that must not be copied:

- authentication is disabled when no JWT secret is configured
- client-supplied entity identifiers can influence ownership behavior
- JWT validation is limited and does not enforce a complete enterprise identity policy
- CORS is configured broadly
- unknown file types can fall back to a text loader
- raw internal errors can reach API clients

V1 will be explicitly described as a local, single-user development application. It will not pretend to provide enterprise authentication.

Authentication must be added before any shared or public deployment.

### 4.12 Logging Findings

Positive ingestion logs include:

- route name
- document identifier
- filename
- content type
- chunk count
- elapsed time
- insertion count
- process memory information
- rollback state

These operational fields are useful.

Unsafe or unnecessary logging includes:

- query text in some exception messages
- complete tracebacks in normal application logs
- temporary filesystem paths
- user or entity information without a privacy policy

The V1 will never log document content, retrieved chunks, complete prompts, answers, embeddings, API keys, or raw query text.

### 4.13 Testing Findings

The repository has meaningful tests for:

- API routes
- Pydantic models
- configuration
- middleware
- path traversal
- concurrent upload isolation
- document loaders
- vector-store behavior
- PGVector filtering
- database health
- batch memory limits
- batch ordering
- cancellation
- rollback
- parallel failure behavior

This is stronger than the testing structure of the smaller educational repository.

The V1 will adopt the test categories that match its smaller scope.

### 4.14 Main Architectural Weakness

`app/routes/document_routes.py` contains more than 1,500 lines.

It combines:

- HTTP routes
- authorization decisions
- file handling
- document loading
- text splitting
- metadata creation
- batch processing
- rollback
- retrieval
- context reconstruction
- logging helpers

This makes the route layer too large and creates tight coupling.

Our most important improvement will be moving these responsibilities into focused services and adapters.

---

## 5. Selected V1 Architecture

### 5.1 Architecture Style

The V1 will be a modular monolith.

It will be:

- one FastAPI application
- one Python process
- one local metadata database
- one local vector store
- one embedding provider
- one answer-generation provider
- no external worker system

This architecture is small enough to understand and test while retaining clean module boundaries.

### 5.2 Proposed Directory Structure

```text
03_rag_project/
├── app/
│   ├── main.py
│   ├── api/
│   │   ├── dependencies.py
│   │   └── routers/
│   │       ├── documents.py
│   │       ├── retrieval.py
│   │       └── health.py
│   ├── core/
│   │   ├── config.py
│   │   ├── exceptions.py
│   │   └── logging.py
│   ├── domain/
│   │   ├── document.py
│   │   ├── chunk.py
│   │   └── citation.py
│   ├── schemas/
│   │   ├── documents.py
│   │   ├── retrieval.py
│   │   ├── answers.py
│   │   └── errors.py
│   ├── services/
│   │   ├── ingestion_service.py
│   │   ├── retrieval_service.py
│   │   └── answer_service.py
│   ├── document_processing/
│   │   ├── loaders.py
│   │   └── chunker.py
│   ├── providers/
│   │   ├── embedding_provider.py
│   │   └── llm_provider.py
│   └── storage/
│       ├── document_repository.py
│       └── vector_store.py
├── data/
│   ├── uploads/
│   ├── qdrant/
│   └── app.db
├── tests/
│   ├── unit/
│   ├── integration/
│   └── evaluation/
├── docs/
├── .env.example
├── requirements.txt
└── README.md
```

### 5.3 Dependency Direction

```text
FastAPI routers
      ↓
application services
      ↓
domain models and interfaces
      ↓
provider and storage adapters
```

Rules:

- routers may call services
- services may use domain models and interfaces
- storage and provider modules implement interfaces
- services must not import FastAPI
- domain models must not import FastAPI, Qdrant, or provider SDKs
- provider SDK objects must not leak into API responses
- `main.py` is responsible for creating and connecting components

---

## 6. Architecture Decision Records

### ADR-001: Use a Modular FastAPI Monolith

Decision:

Use one FastAPI application with clear internal modules.

Reason:

The project does not need distributed services. A modular monolith is easier to run, explain, test, and debug.

Rejected:

- microservices
- separate ingestion service
- separate retrieval service
- distributed workers

### ADR-002: Use Synchronous Ingestion Semantics

Decision:

A document upload request will finish only after parsing, chunking, embedding, and storage complete.

Blocking library calls will run outside the event loop where necessary.

Reason:

V1 documents and evaluation data are small. Synchronous behavior makes failures and API behavior easier to understand.

Deferred:

- Celery
- RabbitMQ
- Redis
- background job status APIs
- parallel ingestion consumers

### ADR-003: Support TXT and PDF First

Decision:

V1 accepts:

- UTF-8 text files
- text-based PDF files

Reason:

These formats are sufficient to demonstrate the complete pipeline.

Rejected for V1:

- DOCX
- XLSX
- PPTX
- EPUB
- XML
- image OCR
- scanned PDFs
- source-code repositories
- web crawling

### ADR-004: Use Qdrant Local Persistent Mode

Decision:

Use Qdrant local mode with an on-disk path for V1 vector storage.

Reason:

- it does not require Docker
- it does not require a separate database server
- it supports persistent local storage
- it supports metadata payloads and filtering
- it is sufficient for a small V1 collection
- it offers a future path to a standalone Qdrant server

The official documentation describes local mode as suitable for testing, debugging, and small vector collections.

Rejected for V1:

- PostgreSQL with PGVector
- MongoDB Atlas
- Elasticsearch
- a Docker-hosted vector database
- several interchangeable vector stores

Limit:

The local mode decision must be reconsidered before production or large-scale deployment.

### ADR-005: Use SQLite for Document Records

Decision:

Use SQLite for document-level records and ingestion status.

Reason:

SQLite is included with Python, requires no external service, and provides reliable structured metadata for a local MVP.

SQLite stores:

- document identity
- original filename
- media type
- size
- SHA-256 hash
- ingestion status
- chunk count
- creation time
- stored file location

Qdrant stores chunk text, vectors, and retrieval metadata.

### ADR-006: Use One Provider Implementation at a Time

Decision:

Define small embedding and LLM provider interfaces, but configure only one implementation of each for V1.

Reason:

Interfaces prevent provider SDKs from spreading across the project. Multiple active implementations would add testing and configuration work without improving the MVP.

Deferred:

- provider factories with many choices
- automatic provider discovery
- provider fallback
- per-request provider selection

The initial concrete providers will be selected during environment setup according to available credentials and hardware.

### ADR-007: Preserve Explicit Document and Chunk Metadata

Decision:

Every chunk must include:

- `document_id`
- `chunk_id`
- `chunk_index`
- `filename`
- `page_number`, when available
- `content_hash`

Reason:

Retrieval, deletion, ordering, evaluation, and citations depend on reliable metadata.

Raw local filesystem paths must not appear in API responses.

### ADR-008: Use Document-Scoped Retrieval

Decision:

Search requests may specify one or more `document_id` values.

The vector search must filter by those identifiers before returning results.

Reason:

This is the strongest pattern from Repository 1. It prevents unrelated documents from entering the answer context and supports user-selected source files.

### ADR-009: Generate Citations from Retrieved Chunks

Decision:

The application, not the LLM, constructs citation objects.

Each citation contains:

- citation number
- document ID
- filename
- page number, when available
- chunk ID
- short excerpt
- retrieval score

Reason:

An LLM must not invent filenames, pages, or source identifiers.

The answer prompt may refer to numbered sources, but the final citation metadata comes directly from retrieved chunks.

### ADR-010: Use Sequential Rollback

Decision:

Each ingestion receives a unique document ID.

If ingestion fails:

1. delete any Qdrant points belonging to that document ID
2. mark the SQLite document record as failed or remove it
3. remove the temporary file
4. return a safe error response

Reason:

This adopts Repository 1’s compensating rollback idea without its parallel pipeline.

### ADR-011: Use Typed Application Exceptions

Decision:

Services raise typed exceptions such as:

- `DocumentNotFoundError`
- `UnsupportedFileTypeError`
- `FileTooLargeError`
- `DocumentParseError`
- `EmbeddingProviderError`
- `VectorStoreError`
- `AnswerProviderError`

A global FastAPI handler maps these exceptions to stable error responses.

Reason:

Services should not return ad hoc error dictionaries or expose raw exception strings.

### ADR-012: Use Privacy-Safe Structured Logging

Decision:

Application logs use stable event names and structured fields.

Allowed fields include:

- request ID
- route
- method
- response status
- document ID
- filename
- media type
- file size
- chunk count
- result count
- provider name
- elapsed time
- error category

Prohibited fields include:

- document content
- chunk content
- raw query text
- complete prompts
- generated answers
- embeddings
- API keys
- authorization tokens
- local file paths
- full user-provided metadata

### ADR-013: Keep V1 Single-User and Local

Decision:

V1 does not implement authentication or multi-tenancy.

Reason:

A minimal JWT implementation can create a false impression of enterprise security.

Requirements before shared deployment:

- authenticated identity provider
- authorization rules
- tenant isolation
- restricted CORS
- rate limits
- audit policy
- secret management
- encrypted network connections
- security review

### ADR-014: Isolate Framework Dependencies

Decision:

LangChain or other orchestration libraries may be used inside adapters, loaders, or the chunker, but their objects must not become domain models or API response types.

Reason:

This keeps the project architecture understandable and reduces dependence on changing framework APIs.

---

## 7. V1 API Contract

| Method | Endpoint | Purpose | Success |
|---|---|---|---:|
| `GET` | `/health` | Check application and storage health | 200 |
| `POST` | `/api/v1/documents` | Upload and synchronously ingest one document | 201 |
| `GET` | `/api/v1/documents` | List ingested documents | 200 |
| `GET` | `/api/v1/documents/{document_id}` | Read document metadata | 200 |
| `DELETE` | `/api/v1/documents/{document_id}` | Delete document record and vectors | 204 |
| `POST` | `/api/v1/search` | Retrieve relevant chunks | 200 |
| `POST` | `/api/v1/answers` | Generate an answer with citations | 200 |

The V1 will not create overlapping upload endpoints.

---

## 8. Core Data Models

### Document Record

```text
document_id: UUID
filename: string
media_type: string
size_bytes: integer
sha256: string
status: processing | ready | failed
chunk_count: integer
stored_path: string
created_at: datetime
updated_at: datetime
```

### Chunk Record

```text
chunk_id: UUID
document_id: UUID
chunk_index: integer
text: string
page_number: integer | null
filename: string
content_hash: string
```

### Retrieval Result

```text
chunk_id: UUID
document_id: UUID
filename: string
page_number: integer | null
text: string
score: float
```

### Citation

```text
citation_number: integer
document_id: UUID
chunk_id: UUID
filename: string
page_number: integer | null
excerpt: string
score: float
```

### Answer Response

```text
answer: string
citations: list[Citation]
retrieval_count: integer
```

---

## 9. V1 Ingestion Flow

```text
POST document
    ↓
validate size, extension, and media type
    ↓
create document ID and safe temporary path
    ↓
stream upload to disk
    ↓
calculate SHA-256
    ↓
create SQLite record with processing status
    ↓
parse TXT or PDF
    ↓
split text with overlap
    ↓
remove empty chunks
    ↓
attach document and page metadata
    ↓
generate embeddings in small sequential batches
    ↓
write points to local Qdrant
    ↓
update SQLite status to ready
    ↓
return document response
```

Failure path:

```text
failure
    ↓
delete Qdrant points for document ID
    ↓
mark document failed
    ↓
remove temporary artifacts
    ↓
log safe error category
    ↓
return stable API error
```

---

## 10. V1 Retrieval and Answer Flow

```text
question + selected document IDs
    ↓
validate that documents exist and are ready
    ↓
generate query embedding
    ↓
search Qdrant with document_id filter
    ↓
apply top-k and optional score threshold
    ↓
return no-evidence result when nothing relevant is found
    ↓
construct numbered context blocks
    ↓
ask LLM to answer only from supplied evidence
    ↓
construct citation objects from retrieved chunk metadata
    ↓
return answer and citations
```

The system must not silently search every document when the request specifies document IDs.

---

## 11. Error Policy

All errors use a stable structure:

```json
{
  "error": {
    "code": "DOCUMENT_NOT_FOUND",
    "message": "The requested document was not found.",
    "request_id": "..."
  }
}
```

| Status | Use |
|---:|---|
| 400 | File exists but cannot be parsed, invalid document operation, or malformed non-schema input |
| 404 | Document ID does not exist |
| 409 | Duplicate document conflict or invalid document state |
| 413 | Uploaded file exceeds the configured maximum |
| 415 | Unsupported file type |
| 422 | FastAPI request-schema validation failure |
| 502 | Embedding or LLM provider failure |
| 503 | Vector store or required service unavailable |
| 500 | Unexpected internal error with a generic client message |

Raw exception strings and stack traces must never be returned to clients.

---

## 12. Logging Policy

Example safe ingestion event:

```text
event=document_ingestion_completed
request_id=...
document_id=...
filename=policy.pdf
media_type=application/pdf
size_bytes=...
chunk_count=...
elapsed_ms=...
```

Example safe failure event:

```text
event=document_ingestion_failed
request_id=...
document_id=...
error_type=DocumentParseError
elapsed_ms=...
```

The application may record a traceback in restricted development logs, but the API response remains generic.

Queries, document content, prompts, and answers are not logged.

---

## 13. Testing Strategy

### Unit Tests

Required unit tests:

- file type validation
- file size validation
- safe path creation
- path traversal rejection
- TXT loading
- PDF loading
- chunk size and overlap
- empty-chunk removal
- metadata preservation
- SHA-256 generation
- citation construction
- exception-to-status mapping
- logging field filtering

### Integration Tests

Required integration tests:

- upload and ingest TXT
- upload and ingest PDF
- SQLite document record creation
- Qdrant point creation
- document-scoped search
- multi-document search
- answer response with citations
- document deletion
- ingestion rollback
- temporary-file cleanup
- health endpoint behavior
- provider failure mapping

Integration tests must use temporary SQLite and Qdrant directories.

### Security Tests

Required security tests:

- `../` traversal filenames
- absolute-path filenames
- unsupported binary files
- oversized uploads
- conflicting file extension and media type
- secret values excluded from responses
- content excluded from logs

---

## 14. Minimum Evaluation Set

Before the MVP is considered complete, create at least:

- 10 valid source documents
- at least 4 PDFs
- at least 4 text files
- at least 2 multi-page documents
- 20 evaluation questions

The questions must include:

- 10 direct-answer questions
- 4 questions requiring evidence from more than one chunk
- 2 questions that test document-scope isolation
- 4 unanswerable questions

Minimum acceptance criteria:

- all valid documents ingest successfully
- no empty chunks are stored
- deleted documents disappear from retrieval
- no result comes from an unselected document
- the expected source appears in the top five results for at least 80% of answerable questions
- every returned citation refers to an actual retrieved chunk
- filename and page metadata are correct when the source provides page information
- unanswerable questions do not receive unsupported factual answers
- API errors never expose secrets, paths, prompts, document content, or tracebacks

---

## 15. Explicitly Deferred Features

The following are outside V1:

- Docker deployment
- PostgreSQL
- PGVector
- MongoDB
- Elasticsearch
- Celery
- RabbitMQ
- Redis
- background ingestion jobs
- parallel ingestion consumers
- multiple vector stores
- multiple active embedding providers
- multiple active LLM providers
- reranking
- hybrid search
- OCR
- scanned-document support
- DOCX, XLSX, PPTX, EPUB, and XML
- agents
- tools
- MCP
- text-to-SQL
- multimodal models
- web crawling
- frontend application
- enterprise authentication
- multi-tenancy
- monitoring dashboards
- Kubernetes
- cloud-specific deployment

A deferred feature will be added only after a measured V1 limitation justifies it.

---

## 16. Adopted and Rejected Reference Patterns

| Reference Pattern | Decision |
|---|---|
| Repository 1 file-scoped retrieval | Adopt as document-scoped retrieval |
| Repository 1 metadata preservation | Adopt |
| Repository 1 unique temporary uploads | Adopt |
| Repository 1 path validation | Adopt |
| Repository 1 lifespan cleanup | Adopt |
| Repository 1 rollback identity | Adopt in simplified form |
| Repository 1 parallel ingestion | Defer |
| Repository 1 global provider objects in config | Reject |
| Repository 1 large route module | Reject |
| Repository 1 overlapping upload routes | Reject |
| Repository 1 raw exception responses | Reject |
| PrivateGPT route/service/component separation | Adopt |
| PrivateGPT structured source blocks | Adopt in simplified form |
| PrivateGPT local Qdrant option | Adopt |
| PrivateGPT agent and tool platform | Reject for V1 |
| RAGFlow enterprise deployment architecture | Defer |
| Mini-RAG staged upload/process/index/search flow | Adopt conceptually |
| Mini-RAG simple splitter implementation | Reject |
| Mini-RAG full prompt in API response | Reject |
| Mini-RAG worker and monitoring infrastructure | Reject for V1 |

---

## 17. Final Architecture Decision

The V1 will be a small, explainable FastAPI application with:

- synchronous TXT and PDF ingestion
- SQLite document records
- locally persisted Qdrant vectors
- explicit document and chunk metadata
- document-scoped retrieval
- one embedding provider
- one answer-generation provider
- structured citations
- typed errors
- privacy-safe logging
- focused unit and integration tests
- a small evaluation dataset

The project will borrow Repository 1’s retrieval scope and ingestion safety while correcting its route-layer coupling and error-handling problems.

PrivateGPT contributes the service-boundary and citation patterns.

RAGFlow and Mini-RAG primarily define the complexity and quality boundaries that V1 must avoid.

---

## 18. Next Implementation Activity

The architecture research phase is sufficiently complete to begin implementation planning.

The next activity is to create the V1 project skeleton and configuration without installing large model or database dependencies.

The first implementation checkpoint should contain:

1. directory structure
2. typed settings
3. FastAPI application factory
4. health endpoint
5. error response model
6. document and chunk domain models
7. empty provider and storage interfaces
8. initial unit-test structure

No vector database, embedding model, or LLM dependency should be installed until the skeleton and interfaces have been reviewed.

---

## 19. Sources

- Main reference repository: https://github.com/danny-avila/rag_api
- Reviewed main-reference commit: https://github.com/danny-avila/rag_api/commit/4985b37b8b5d4519d68eceedfef1e63624012f9d
- Main-reference README: https://github.com/danny-avila/rag_api/blob/main/README.md
- FastAPI entry point: https://github.com/danny-avila/rag_api/blob/main/main.py
- Document routes and ingestion pipeline: https://github.com/danny-avila/rag_api/blob/main/app/routes/document_routes.py
- Configuration and provider creation: https://github.com/danny-avila/rag_api/blob/main/app/config.py
- Security middleware: https://github.com/danny-avila/rag_api/blob/main/app/middleware.py
- Document loaders: https://github.com/danny-avila/rag_api/blob/main/app/utils/document_loader.py
- Vector-store factory: https://github.com/danny-avila/rag_api/blob/main/app/services/vector_store/factory.py
- Async PGVector wrapper: https://github.com/danny-avila/rag_api/blob/main/app/services/vector_store/async_pg_vector.py
- Database lifecycle: https://github.com/danny-avila/rag_api/blob/main/app/services/database.py
- Main-reference tests: https://github.com/danny-avila/rag_api/tree/main/tests
- Secondary reference: https://github.com/zylon-ai/private-gpt
- Enterprise boundary reference: https://github.com/infiniflow/ragflow
- Educational reference: https://github.com/bakrianoo/mini-rag

---

## 20. V2 Evaluation and Portfolio Decisions (2026-08-10)

V2 did not expand the production API boundary. It strengthened the evidence for
the existing architecture through a typed 50-question evaluation set, retrieval
metrics, isolated experiments, bad-case analysis, and local latency measurement.

Adopted evaluation decisions:

- keep V1 document-scoped semantic Dense retrieval in the production service
- use exact evidence snippets rather than filenames alone as retrieval ground truth
- report Hit@K, Recall@K, and MRR separately
- isolate every chunk, Top-K, provider, and ranking experiment in fresh stores
- treat `0.37` through `0.41` only as a synthetic semantic-threshold candidate interval
- keep production threshold configuration unchanged until broader validation
- retain ambiguous questions as a visible clarification-product gap
- store latency separately from deterministic quality reports

Measured retrieval decisions:

- hashing baseline: Recall@5 `82.50%`, MRR `0.7937`
- OpenAI `text-embedding-3-small`: Recall@5 `100%`, MRR `0.9833`
- equal-weight semantic Dense + BM25/RRF: Recall@5 `92.50%`, MRR `0.8438`
- reject the Hybrid prototype because it introduces three answerable retrieval regressions

The negative Hybrid result is part of the portfolio evidence. Complexity is not
promoted merely because it is available; a candidate must improve the measured
quality boundary without creating unacceptable refusal or ranking regressions.

V2 remains local and single-user. Authentication, multi-tenancy, asynchronous
ingestion, OCR, frontend work, managed databases, and public deployment remain
outside the frozen release.
- Qdrant local-mode documentation: https://qdrant.tech/documentation/frameworks/langchain/

---

## 21. Multi-LLM Generation Enhancement (2026-08-11)

This bounded enhancement supersedes only the earlier single-LLM-implementation
constraint. The service still activates one LLM backend at a time, but the
existing `LLMProvider` port can now select OpenAI or DeepSeek through typed
configuration. OpenAI embedding, chunking, Qdrant retrieval, document scope,
the grounded prompt, refusal marker, and application-built citations remain
unchanged.

DeepSeek uses the existing OpenAI Python SDK against the official
OpenAI-compatible Responses API. The selected model is
`deepseek-v4-flash`; legacy `deepseek-chat` and `deepseek-reasoner` identifiers
are not used. Provider results now include optional normalized token usage so
the same application contract supports latency and cost reporting without
leaking credentials or prompts into logs.

The comparison experiment reuses the tracked 10-document, 50-question corpus.
Retrieval runs once per question, and both generation providers receive the
same evidence blocks. Automatic answer quality is reported as a limited
reference-answer token-F1 proxy, not as production accuracy. Real API calls
remain opt-in, require both credentials, use only synthetic data, and are never
part of CI.
