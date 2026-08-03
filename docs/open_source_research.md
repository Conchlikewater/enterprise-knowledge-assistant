# Open-Source RAG Project Research

## 1. Research Goal

This research supports the architecture design of the planned **Enterprise Knowledge Assistant**.

The purpose is not to copy an existing repository. The goals are to:

- understand how real RAG projects are structured
- identify reusable engineering patterns
- compare document ingestion and retrieval designs
- understand how FastAPI is used in AI applications
- determine an achievable V1 scope
- record which designs should and should not be adopted

The research phase will stop once there is enough evidence to design and explain the project’s own V1 architecture.

---

## 2. Research Strategy

The repositories will be studied at three levels.

### Level A: Quick Review

Expected number: approximately 4–6 repositories.

Time limit: 20–30 minutes per repository.

Focus:

- project purpose
- main features
- technology stack
- repository structure
- apparent complexity
- relevance to the planned project

### Level B: Local Run and Functional Review

Expected number: up to 2 repositories, where practical.

Focus:

- installation process
- required external services
- environment variables
- startup procedure
- API behaviour
- document ingestion workflow
- retrieval workflow
- practical difficulties

A repository may remain at Level A if local execution requires unsuitable system changes or excessive dependencies.

### Level C: Architecture Analysis

Expected number: 1 main reference repository.

Focus:

- module boundaries
- request flow
- data flow
- dependency direction
- error handling
- logging
- configuration management
- testing strategy
- designs worth adopting
- designs that are unnecessarily complex for V1

---

## 3. Evaluation Dimensions

| Dimension | Main Question |
|---|---|
| Project purpose | What problem does the repository solve? |
| Target users | Who is expected to use the system? |
| Main features | Which parts of a complete RAG workflow are implemented? |
| API design | How are ingestion and retrieval exposed? |
| Document ingestion | How are files loaded, validated and processed? |
| Chunking | Which splitting strategy and defaults are used? |
| Embeddings | Which embedding providers and models are supported? |
| Vector storage | Which vector databases are supported? |
| Metadata | How are documents, chunks, users and sources identified? |
| Retrieval | How are searches filtered and ranked? |
| LLM integration | Does the repository generate answers or only retrieve context? |
| Async design | Which operations are asynchronous or moved to workers? |
| Configuration | How are secrets and runtime options managed? |
| Error handling | How are invalid input and operational failures represented? |
| Logging | What lifecycle and diagnostic information is recorded? |
| Testing | What unit, integration or evaluation tests exist? |
| Deployment | Can the project run locally, in Docker or in the cloud? |
| Complexity | Which features would be excessive for our V1? |
| Relevance | Which designs can support our Enterprise Knowledge Assistant? |

---

## 4. Repository Summary Table

| No. | Repository | Review Level | Main Purpose | Main Stack | Local Run | Relevance | Status |
|---:|---|---|---|---|---|---|---|
| 1 | `danny-avila/rag_api` | Level A | File-ID-based ingestion and vector retrieval API | FastAPI, LangChain, PostgreSQL/pgvector | Deferred: Docker unavailable | High | Completed |
| 2 | To be selected | Level B/C candidate |  |  | Not tested |  | Pending |
| 3 | To be selected | Level A |  |  | Not tested |  | Pending |
| 4 | To be selected | Level A |  |  | Not tested |  | Pending |
| 5 | Optional | Level A |  |  | Not tested |  | Pending |
| 6 | Optional | Level A |  |  | Not tested |  | Pending |

The repository count is flexible. Research will stop when the planned V1 architecture can be justified clearly.

---

## 5. Repository Reviews

# Repository 1: danny-avila/rag_api

### 1. Basic Information

- Repository: https://github.com/danny-avila/rag_api
- Default branch: `main`
- License: MIT
- Review date: 2026-08-02
- Latest reviewed commit: `12a4469`
- Latest observed commit date: 2026-06-18
- Project type: ID-based RAG API
- Primary integration target: LibreChat
- Review level completed: Level A

### 2. Project Purpose

The repository provides a standalone FastAPI service for document ingestion and vector retrieval.

Its main design feature is the use of `file_id`. Document chunks are stored with file-level metadata, allowing an external application to restrict retrieval to one or more selected files.

The repository focuses on ingestion and retrieval. It does not implement the complete conversational workflow that sends retrieved context to an LLM and generates a final cited answer.

### 3. Main Features

- upload and index documents
- index files already located in the configured upload directory
- split documents into chunks
- generate embeddings
- store and retrieve vectors using `file_id`
- query one file or multiple files
- retrieve stored document context
- delete indexed documents
- perform health checks
- optionally verify JWTs
- process embedding batches asynchronously
- attempt rollback when batch ingestion fails
- support PostgreSQL/pgvector and MongoDB Atlas Vector Search
- run unit and integration tests with pytest

### 4. Repository Structure

```text
rag_api/
├── app/
│   ├── routes/
│   │   ├── document_routes.py
│   │   └── pgvector_routes.py
│   ├── services/
│   │   ├── database.py
│   │   ├── mongo_client.py
│   │   └── vector_store/
│   │       ├── async_pg_vector.py
│   │       ├── atlas_mongo_vector.py
│   │       ├── extended_pg_vector.py
│   │       └── factory.py
│   ├── utils/
│   ├── config.py
│   ├── constants.py
│   ├── middleware.py
│   └── models.py
├── tests/
├── utils/docker/
├── Dockerfile
├── Dockerfile.lite
├── docker-compose.yaml
├── api-compose.yaml
├── db-compose.yaml
├── main.py
├── requirements.txt
├── requirements.lite.txt
└── test_requirements.txt
```

The structure separates application configuration, middleware, API routes, database services and vector-store implementations.

However, `document_routes.py` is very large and contains several responsibilities that could be separated further.

### 5. Technology Stack

| Category | Technology |
|---|---|
| Language | Python |
| Web framework | FastAPI 0.115.12 |
| ASGI server | Uvicorn 0.28.0 |
| RAG framework | LangChain 1.x |
| Default vector database | PostgreSQL with pgvector |
| Alternative vector database | MongoDB Atlas Vector Search |
| Database access | SQLAlchemy, asyncpg and psycopg2 |
| Data validation | Pydantic 2 |
| Document parsing | Unstructured, PyPDF, Pandoc, docx2txt, pandas, openpyxl and python-pptx |
| Authentication | Optional JWT verification |
| Deployment | Docker and Docker Compose |
| Container Python version | Python 3.12 |
| Testing | pytest |

The current README lists these embedding providers:

- OpenAI
- Azure OpenAI
- AWS Bedrock
- Hugging Face
- Hugging Face TEI
- Ollama
- Google GenAI
- Google Vertex AI

### 6. Run Requirements

The default setup requires:

- a configured `.env` file
- PostgreSQL with the pgvector extension
- an embedding provider
- an API key when using a hosted provider such as OpenAI
- Python dependencies from `requirements.txt`, or Docker
- Pandoc and NLTK resources for some document loaders

The full Docker Compose configuration starts PostgreSQL/pgvector and the FastAPI service.

Default port mappings include:

- FastAPI: host port `8000`
- PostgreSQL: host port `5433` mapped to container port `5432`

The README also documents local startup using `requirements.txt` followed by `uvicorn main:app`.

Some clean-install examples in the README use Linux/macOS commands and should not be copied directly into Windows PowerShell.

Important default configuration includes:

| Setting | Default |
|---|---|
| Vector database | `pgvector` |
| Embedding provider | `openai` |
| OpenAI embedding model | `text-embedding-3-small` |
| Collection name | `testcollection` |
| Chunk size | `1500` |
| Chunk overlap | `100` |
| Embedding batch size | `500` |
| Maximum queued batches | `3` |
| Parallel consumers per file | `2` |
| Upload directory | `./uploads/` |
| API host | `0.0.0.0` |
| API port | `8000` |

### 7. Main API Routes

| Route | Purpose |
|---|---|
| `GET /health` | Check service health |
| `GET /ids` | List stored IDs |
| `GET /documents` | Retrieve documents by IDs |
| `DELETE /documents` | Delete indexed documents |
| `POST /embed` | Upload and index a file |
| `POST /local/embed` | Index a file from the upload directory |
| `POST /embed-upload` | Alternative upload-and-index route |
| `POST /query` | Retrieve chunks from one file ID |
| `POST /query_multiple` | Retrieve chunks from multiple file IDs |
| `GET /documents/{id}/context` | Reconstruct stored document context |
| `POST /text` | Extract document text |

### 8. Core Ingestion Flow

```text
HTTP file upload
→ validate and create a temporary file path
→ save the uploaded file
→ select a document loader
→ load document content
→ split content into overlapping chunks
→ attach file_id, user_id, digest and source metadata
→ generate embeddings
→ insert chunks into the vector store
→ return file information
→ remove the temporary file
```

The splitter is based on `RecursiveCharacterTextSplitter`.

Each stored chunk contains metadata including:

- `file_id`
- `user_id`
- a digest of the chunk content
- metadata supplied by the document loader

When batching is enabled, the pgvector implementation uses a bounded asynchronous producer-consumer pipeline.

If ingestion fails after some chunks have been inserted, the service attempts to remove the chunks created by that ingestion attempt.

### 9. Core Retrieval Flow

```text
query text and file_id
→ generate or reuse a cached query embedding
→ perform vector similarity search
→ filter records by file_id
→ optionally apply a distance threshold
→ check document ownership metadata
→ return matching chunks and scores
```

The single-file query route filters by one `file_id`.

The multiple-file query route filters against a list of file IDs.

This repository retrieves relevant chunks but does not generate the final LLM answer. Another component, such as LibreChat, is expected to use the retrieved chunks as context.

### 10. Designs Worth Adopting

1. Store `document_id` or `file_id` in every chunk’s metadata.
2. Separate FastAPI routes from vector-store implementations.
3. Hide vector-store selection behind an interface or factory.
4. Validate uploaded file paths.
5. Clean temporary files after processing.
6. Add health checks and ingestion lifecycle logging.
7. Move blocking work away from the asynchronous event loop.
8. Add cleanup or rollback behaviour for partially failed ingestion.
9. Include unit and integration tests for ingestion.

### 11. Designs Not Suitable for Our V1

1. Supporting many embedding providers immediately.
2. Supporting both PostgreSQL and MongoDB vector stores.
3. Implementing complex multi-consumer batch processing before it is needed.
4. Adding cloud-specific database configuration to the first version.
5. Providing several overlapping upload endpoints.
6. Placing routing, file handling, chunking and storage logic in one large module.

### 12. Local Run Decision

The Docker check produced the following result:

```text
docker was not recognised as an available command
```

Docker is therefore not installed or is not available through the system PATH.

The repository will not be run locally during the current quick-review stage.

The full dependency set will also not be installed into the existing foundations virtual environment because this could create unnecessary dependency conflicts.

Current decision:

- Level A review: completed
- Level B local run: deferred
- Architecture relevance: high
- Possible deeper review: reconsider after comparing additional repositories

### 13. One-Sentence Conclusion

> `danny-avila/rag_api` is a highly relevant example of a file-scoped ingestion and retrieval service, but its provider support, configuration surface and ingestion concurrency are more complex than our V1 requires.

### 14. Sources

- Repository and README: https://github.com/danny-avila/rag_api
- Application directory: https://github.com/danny-avila/rag_api/tree/main/app
- Dependencies: https://github.com/danny-avila/rag_api/blob/main/requirements.txt
- Docker Compose: https://github.com/danny-avila/rag_api/blob/main/docker-compose.yaml
- API entry point: https://github.com/danny-avila/rag_api/blob/main/main.py
- Document routes: https://github.com/danny-avila/rag_api/blob/main/app/routes/document_routes.py
- Commit history: https://github.com/danny-avila/rag_api/commits/main/

---

## 6. Preliminary V1 Questions

The research should eventually answer these questions:

1. Should V1 support uploads through an API or import files from a local directory?
2. Which document formats should be supported first?
3. Should document parsing, chunking, embedding and storage be synchronous?
4. Which vector storage option is simplest and sufficient for V1?
5. How should document and chunk metadata be represented?
6. How should source citations be returned?
7. Which modules should be separated from the FastAPI routing layer?
8. Which errors should return 400, 404, 422 or 500?
9. What should be logged without exposing document content?
10. What is the minimum evaluation set required before the MVP is considered complete?

---

## 7. Research Completion Criteria

The research phase is complete when:

- at least four relevant repositories have received a quick review
- up to two suitable repositories have received a local functional review, where practical
- one main reference repository has received deeper architecture analysis
- important findings have been recorded with source links
- adopted and rejected design decisions can be explained
- the planned V1 architecture and scope can be justified clearly

---

## 8. Repository 2: infiniflow/ragflow

### 1. Basic Information

- Repository: https://github.com/infiniflow/ragflow
- Default branch: `main`
- License: Apache License 2.0
- Review date: 2026-08-02
- Project version observed in `pyproject.toml`: `0.26.4`
- Latest observed commit: `8db965f`
- Latest observed commit date: 2026-08-01
- Project type: Full-stack enterprise RAG and Agent platform
- Review level completed: Level A

### 2. Project Purpose

RAGFlow is a complete RAG platform rather than a small API example.

It combines:

- document upload and management
- document parsing and OCR
- configurable chunking
- embeddings
- hybrid retrieval
- reranking
- citation generation
- knowledge-base management
- chat and answer generation
- visual ingestion pipelines
- Agent workflows
- a web user interface
- public APIs and SDKs

It is useful as an enterprise product and architecture reference, but its overall scope is much larger than the planned V1.

### 3. Main Features

- deep document understanding
- OCR, layout recognition and table structure recognition
- template-based chunking
- visual inspection and editing of chunks
- grounded answers with traceable citations
- support for Word, PDF, slides, spreadsheets, text, images, scanned documents, structured data and web pages
- configurable embedding and LLM providers
- hybrid full-text and vector retrieval
- optional reranking models
- document and knowledge-base filtering
- GraphRAG and RAPTOR-related features
- visual ingestion pipelines
- Agent workflows and templates
- external data-source synchronisation
- API, Python SDK and web interface
- authentication and multi-user data management

### 4. High-Level Repository Structure

```text
ragflow/
├── admin/              # Administration functions
├── agent/              # Agent workflow and plugin code
├── api/                # HTTP application, routes and database services
│   └── apps/
│       ├── auth/
│       ├── restful_apis/
│       └── services/
├── common/             # Shared configuration and utilities
├── deepdoc/            # OCR, layout recognition and document parsers
│   ├── parser/
│   ├── server/
│   └── vision/
├── docker/             # Docker Compose and service configuration
├── docs/               # Documentation
├── helm/               # Kubernetes deployment resources
├── mcp/                # MCP integration
├── memory/             # Agent/user memory features
├── rag/
│   ├── advanced_rag/
│   ├── flow/
│   ├── graphrag/
│   ├── llm/
│   ├── nlp/
│   ├── prompts/
│   └── svr/
├── sdk/
│   └── python/
├── test/               # Test suites
├── web/                # React and TypeScript frontend
├── Dockerfile
├── pyproject.toml
├── uv.lock
├── go.mod
└── go.sum
```

The repository contains Python, TypeScript and Go components. Its large number of top-level modules reflects a mature platform with several independently complex subsystems.

### 5. Technology Stack

| Category | Technology |
|---|---|
| Main backend language | Python 3.13 |
| Backend web framework | Quart |
| API schema | Quart-Schema |
| Authentication | Session, token and API-key mechanisms |
| Frontend | React 18 and TypeScript |
| Frontend build tool | Vite |
| Primary metadata database | MySQL |
| Object storage | MinIO by default |
| Cache, sessions and task coordination | Redis |
| Default document/vector engine | Elasticsearch |
| Alternative document engine | Infinity |
| Document processing | DeepDoc, OCR, layout recognition and parsers |
| RAG implementation | Custom `rag/` modules |
| Deployment | Docker Compose and Helm |
| Python dependency management | `uv` and `pyproject.toml` |
| Additional implementation language | Go |

Important finding: RAGFlow does **not** use FastAPI as its main Python web framework. The application creates a Quart app, dynamically registers blueprints and starts it from `api/ragflow_server.py`.

### 6. Run Requirements

The current README lists these self-hosting prerequisites:

- CPU: at least 4 cores
- RAM: at least 16 GB
- Disk space: at least 50 GB
- Docker: at least version 24.0.0
- Docker Compose: at least version 2.26.1
- Python: at least 3.13
- gVisor: required only for the code-executor sandbox

The default deployment depends on several services, including:

- MySQL
- MinIO
- Redis
- Elasticsearch

Development from source still uses Docker Compose to start the dependent services. It additionally requires Python dependencies, downloaded model resources, frontend Node.js dependencies and separate backend and frontend processes.

Current Docker images target x86 platforms. ARM64 systems require a separate build process.

### 7. Core Ingestion Flow

```text
user uploads a document
→ metadata is recorded in the application database
→ original file is stored through the configured object-storage service
→ a background parsing task is created
→ a task executor retrieves the file
→ the configured parser processes the document
→ OCR, layout or table analysis is applied when required
→ document content is converted into chunks
→ chunk metadata, positions and images are prepared
→ optional keywords, questions or table-of-contents data are generated
→ embeddings are generated in batches
→ chunks and vectors are inserted into Elasticsearch or Infinity
→ document progress and chunk counts are updated
```

The parser is selected from a factory using the dataset or document configuration.

Chunk configuration can include:

- parser type
- target chunk token count
- overlap percentage
- delimiter
- page range
- language
- layout recogniser

Document parsing is handled in background task executors rather than inside the main HTTP request process.

### 8. Core Retrieval Flow

```text
user question
→ select tenant, knowledge base and optional document filters
→ tokenize and analyse the question
→ generate a query embedding
→ perform keyword and vector search
→ fuse full-text and vector scores
→ optionally apply an external reranking model
→ apply similarity thresholds
→ return ranked chunks with document and position metadata
→ use the selected chunks for citations and LLM answer generation
```

The retrieval code supports filters including:

- knowledge-base IDs
- document IDs
- tenant IDs
- availability state
- knowledge-graph fields

Returned chunks can include:

- chunk ID
- chunk text
- document ID and name
- knowledge-base ID
- similarity score
- vector similarity
- term similarity
- page and position information
- image ID
- important keywords

This is considerably more advanced than the file-ID-filtered vector search in Repository 1.

### 9. Architecture Observations

Useful patterns:

1. Separate the HTTP server from background ingestion workers.
2. Keep document parsing in a dedicated subsystem.
3. Store original files separately from searchable chunk indexes.
4. Track ingestion progress explicitly.
5. Select parsing and chunking strategies through configuration.
6. Preserve document, page and position metadata for citations.
7. Combine keyword and vector retrieval.
8. Keep reranking optional.
9. Filter retrieval by tenant, knowledge base and document.
10. Separate frontend, API, ingestion, retrieval and storage responsibilities.

Potential concerns:

1. The platform requires several infrastructure services.
2. Its minimum hardware requirements are high for a learning project.
3. Quart differs from the FastAPI framework planned for our V1.
4. The repository is too large to understand through a quick complete code review.
5. Agent, GraphRAG, RAPTOR, MCP and ingestion-pipeline features greatly increase scope.
6. Supporting multiple document engines and storage backends increases configuration complexity.
7. OCR and layout recognition are resource-intensive.
8. Operating background workers, queues and multiple databases requires production-level operational knowledge.

### 10. Designs Worth Adopting

- separate ingestion work from HTTP routing
- represent ingestion as a visible state or task
- keep original files separate from searchable chunks
- preserve page and position metadata
- return traceable source information
- make retrieval filters explicit
- consider simple hybrid keyword and vector retrieval after the MVP
- define a clean boundary between parsing, indexing, retrieval and answer generation

### 11. Designs Not Suitable for Our V1

- a complete Agent platform
- GraphRAG and RAPTOR
- visual ingestion workflow builders
- multiple document/vector engines
- Kubernetes deployment
- dedicated OCR and layout-recognition services
- several independent databases and storage services
- multi-language Python, TypeScript and Go backend development
- broad external data-source synchronisation
- complex distributed task execution

### 12. Comparison with Repository 1

| Dimension | `danny-avila/rag_api` | `infiniflow/ragflow` |
|---|---|---|
| Scope | Retrieval API | Complete RAG platform |
| Python web framework | FastAPI | Quart |
| Frontend | None | React and TypeScript |
| Main retrieval filter | File ID | Tenant, knowledge base and document |
| Default vector storage | PostgreSQL/pgvector | Elasticsearch |
| Background ingestion | Internal async batching | Dedicated task executors |
| Document processing | Library-based loaders | Dedicated DeepDoc subsystem |
| Answer generation | Not included | Included |
| Citations | Retrieved metadata only | Product-level traceable citations |
| Local setup | Moderate | Heavy |
| V1 similarity | Relatively close | Much larger than required |

### 13. Local Run Decision

RAGFlow will not be run locally during this research stage.

Reasons:

- Docker is unavailable on the current computer.
- The README requires Docker and Docker Compose.
- The minimum documented memory requirement is 16 GB.
- The minimum documented disk requirement is 50 GB.
- Several dependent services must run together.
- A source installation requires Python 3.13 and frontend dependencies.
- Local execution is unnecessary for the initial architecture comparison.

Current decision:

- Level A review: completed
- Level B local run: rejected for the current environment
- Architecture relevance: high
- V1 implementation similarity: low to medium
- Recommended use: enterprise architecture and feature-boundary reference

### 14. One-Sentence Conclusion

> RAGFlow demonstrates how a production-scale RAG platform separates document storage, background parsing, indexing, hybrid retrieval, citations and answer generation, but most of its distributed infrastructure and advanced features should remain outside our V1.

### 15. Sources

- Repository and README: https://github.com/infiniflow/ragflow
- API application: https://github.com/infiniflow/ragflow/blob/main/api/apps/__init__.py
- Server entry point: https://github.com/infiniflow/ragflow/blob/main/api/ragflow_server.py
- Background ingestion executor: https://github.com/infiniflow/ragflow/blob/main/rag/svr/task_executor.py
- Retrieval implementation: https://github.com/infiniflow/ragflow/blob/main/rag/nlp/search.py
- Python configuration: https://github.com/infiniflow/ragflow/blob/main/pyproject.toml
- Frontend configuration: https://github.com/infiniflow/ragflow/blob/main/web/package.json
- Docker Compose: https://github.com/infiniflow/ragflow/blob/main/docker/docker-compose.yml
- Service configuration: https://github.com/infiniflow/ragflow/blob/main/docker/service_conf.yaml.template
- DeepDoc: https://github.com/infiniflow/ragflow/tree/main/deepdoc
- Commit history: https://github.com/infiniflow/ragflow/commits/main/

## 9. Repository 3: zylon-ai/private-gpt

### Basic Information

- Repository: https://github.com/zylon-ai/private-gpt
- Default branch: `main`
- License: Apache-2.0
- Review date: 2026-08-02
- Latest reviewed commit: `0216db9`
- Latest commit date observed: 2026-07-30
- Current package version: `1.0.1`
- Project type: Private AI application API platform
- Initial review level: Level A
- Local-run decision: Level B candidate, pending environment checks

### Project Purpose

PrivateGPT provides an API layer for building private AI applications using locally hosted or externally hosted models.

The current project is broader than a basic RAG demonstration. Its documented capabilities include:

- document ingestion
- semantic retrieval
- source citations
- conversational messages
- tool and skill execution
- MCP connections
- text-to-SQL
- structured data access
- a built-in workbench interface

The repository has been rebuilt as PrivateGPT 1.0. Therefore, older tutorials and architecture descriptions may no longer match the current codebase.

PrivateGPT does not directly run the language model. It connects to an OpenAI-compatible inference server through configured API endpoints.

### Main Features

- Ingest base64-encoded files, remote URIs, or plain text
- Organize documents using collections and artifact identifiers
- Attach custom metadata to documents
- Parse documents into nodes and chunks
- Generate and store embeddings
- Filter retrieval by collection, artifact, and metadata
- Configure retrieval limits and score thresholds
- Expand retrieved chunks with nearby document context
- Return source information for citation generation
- Support synchronous and asynchronous ingestion
- Provide chat, embedding, model, ingestion, content, tool, skill, and health APIs
- Provide a workbench interface under `/ui`

### Technology Stack

| Category | Technology |
|---|---|
| Programming language | Python 3.11 |
| Web framework | FastAPI |
| Dependency injection | Injector |
| RAG framework | LlamaIndex |
| Data validation | Pydantic |
| Default vector storage | Qdrant |
| Default local data directory | `local_data/private_gpt` |
| Model connection | OpenAI-compatible API |
| Local model example | Ollama |
| Package and environment management | `uv` |
| Frontend | Built-in web workbench |
| Optional background processing | Celery and external workers |
| Testing | Pytest |
| License | Apache-2.0 |

The current package configuration requires Python `>=3.11,<3.12`. Python 3.12 or 3.13 is therefore not suitable for the reviewed version.

### Repository Structure

```text
private-gpt/
├── private_gpt/
│   ├── artifact_index/
│   ├── chat/
│   ├── cli/
│   ├── components/
│   │   ├── embedding/
│   │   ├── ingest/
│   │   ├── llm/
│   │   ├── node_store/
│   │   ├── postprocessor/
│   │   ├── readers/
│   │   ├── vector_store/
│   │   └── workflows/
│   ├── server/
│   │   ├── chat/
│   │   ├── content/
│   │   ├── health/
│   │   ├── ingest/
│   │   ├── primitives/
│   │   ├── skills/
│   │   └── tools/
│   ├── settings/
│   ├── launcher.py
│   └── main.py
├── tests/
├── ui/
├── Dockerfile
├── pyproject.toml
├── settings.yaml
└── uv.lock
```

### Application Architecture

The application entry point creates a FastAPI application through a dedicated launcher.

The launcher is responsible for:

- application lifespan management
- dependency injection
- database migrations
- router registration
- authentication dependencies
- exception handling
- request validation
- CORS
- API documentation
- optional workbench mounting

The repository separates HTTP routers, application services, reusable components, and multi-step workflows. This keeps most RAG logic outside the FastAPI routing layer.

### Core Ingestion Flow

The reviewed ingestion flow is:

1. A client sends a request to `/v1/artifacts/ingest`.
2. The request supplies an artifact identifier, collection, input content, and optional metadata.
3. The input can be a base64 file, remote URI, or plain text.
4. The FastAPI router passes the request to the configured ingestion scheduler.
5. The default scheduler can perform the work locally; advanced deployments can use workers.
6. The ingestion service converts the supplied input into processable file data.
7. The parser transforms the document into nodes and chunks.
8. Each node receives metadata such as:
   - artifact identifier
   - collection
   - file hash
   - file metadata
   - embedding model identifier
   - LLM model identifier, where applicable
9. Existing nodes for the same artifact are removed to avoid duplicates.
10. Embeddings and nodes are inserted into the configured indexes.
11. The indexes are persisted.
12. The API returns information about the ingested documents.

The file hash can also be used to detect content that has already been processed.

### Core Retrieval Flow

The reviewed retrieval flow is:

1. The client submits a search or message request.
2. A context filter selects the collection and optional artifact identifiers.
3. The service opens the configured vector and node stores.
4. A LlamaIndex vector retriever performs semantic search.
5. Retrieval can apply:
   - collection filtering
   - artifact filtering
   - custom metadata filtering
   - result limits
   - score thresholds
6. Results are ordered by similarity score.
7. Postprocessors can filter, expand, or shorten the retrieved context.
8. Nearby nodes can be added to provide more complete document context.
9. Retrieved nodes are converted into source blocks.
10. The selected context can be formatted with citations for the final response.

This design preserves a connection between a retrieved chunk and its original artifact, collection, and document metadata.

### Configuration and Default Behavior

The main configuration is stored in `settings.yaml`.

Important reviewed defaults include:

- API port: `8080`
- Swagger documentation: `/docs`
- ReDoc documentation: `/redoc`
- Workbench interface: `/ui`
- Default vector store: Qdrant
- Default vector collection: `zgptvector`
- Default retrieval `top_k`: `32`
- Source citations: enabled
- Authentication: disabled by default
- Local ingestion scheduler: enabled by default
- Local chat and tool scheduling: enabled by default
- Local Qdrant storage can be used when no external Qdrant URL is configured

The configuration makes a basic single-machine setup possible without requiring the complete production worker infrastructure.

### Running Requirements

The current Windows quickstart requires:

- Python 3.11
- the `uv` package and environment tool
- PrivateGPT with its core dependencies
- an OpenAI-compatible inference server
- a chat model endpoint
- an embedding model endpoint
- enough memory and storage for the selected models

Ollama is shown as one possible local inference server, but it is not the only supported option.

Docker is not mandatory for the basic quickstart. This makes the repository more practical for local evaluation than the first two reviewed repositories.

However, the repository must not be installed into the existing foundations virtual environment. A separate environment is required to avoid dependency conflicts.

### Designs Worth Adopting

- Keep FastAPI routers thin and place RAG behavior in services and components.
- Use one clearly defined ingestion request model.
- Represent each document with a collection, artifact identifier, and metadata.
- Keep model, embedding, and vector-store choices behind configurable components.
- Preserve source metadata throughout ingestion and retrieval.
- Return structured source blocks that can support citations.
- Allow a simple local scheduler before introducing external workers.
- Add application lifespan handling, health routes, and centralized error handling.
- Detect duplicate content using a file hash.
- Keep ingestion, retrieval, storage, and API code in separate modules.

### Designs Not Suitable for Our V1

The following features are too complex for the planned first version:

- skills and tool execution
- MCP connections
- text-to-SQL
- multiple background-worker systems
- multiple model and database providers
- advanced multi-tenancy
- complex tree-based document expansion
- configurable agent workflows
- multimodal processing
- extensive production deployment options
- compatibility with several different external API styles

Our V1 should use a much smaller and easier-to-explain ingestion and retrieval pipeline.

### Local Run Decision

Repository 3 is a stronger Level B local-run candidate than the first two repositories because:

- it has documented Windows instructions
- Docker is not mandatory
- FastAPI matches the planned project
- Qdrant can run with local storage
- local scheduling is available
- its ingestion and citation flows are directly relevant

A local run is not approved yet because the environment still needs to be checked for:

- an installed Python 3.11 interpreter
- an available OpenAI-compatible model server
- sufficient resources for a suitable chat and embedding model

Repository 3 is therefore recorded as:

- Level A review: completed
- Level B local run: candidate
- Architecture relevance: high
- V1 scope similarity: medium
- Main limitation: the complete project is much larger than the planned MVP

### One-Sentence Conclusion

> PrivateGPT is a strong FastAPI architecture and local-run reference, especially for ingestion boundaries, metadata filtering, retrieval, and citations, but its full AI platform scope is far beyond the planned V1.

### Sources

- Repository and README: https://github.com/zylon-ai/private-gpt
- Current package configuration: https://github.com/zylon-ai/private-gpt/blob/main/pyproject.toml
- Main settings: https://github.com/zylon-ai/private-gpt/blob/main/settings.yaml
- FastAPI application launcher: https://github.com/zylon-ai/private-gpt/blob/main/private_gpt/launcher.py
- Application directory: https://github.com/zylon-ai/private-gpt/tree/main/private_gpt
- Ingestion routes: https://github.com/zylon-ai/private-gpt/blob/main/private_gpt/server/ingest/ingest_router.py
- Ingestion service: https://github.com/zylon-ai/private-gpt/blob/main/private_gpt/server/ingest/ingest_service.py
- Ingestion component: https://github.com/zylon-ai/private-gpt/blob/main/private_gpt/components/ingest/ingest_component.py
- Vector-store component: https://github.com/zylon-ai/private-gpt/blob/main/private_gpt/components/vector_store/vector_store_component.py
- Retrieval workflow: https://github.com/zylon-ai/private-gpt/blob/main/private_gpt/components/workflows/retrieval/retrieval.py
- Semantic-search workflow: https://github.com/zylon-ai/private-gpt/blob/main/private_gpt/components/workflows/retrieval/semantic_search.py
- Reviewed commit: https://github.com/zylon-ai/private-gpt/commit/0216db9f4adfc21ddbf54fdae21bd3f610a5472f

### Local Run Environment Check Update

The local environment was checked after completing the Level A review.

Observed results:

- Docker: not installed or not available through PATH
- Installed Python version: Python 3.12
- Required Python version: Python 3.11
- Python 3.11: not installed
- Ollama: not installed or not available through PATH
- Existing foundations virtual environment: must not be reused

#### Final Local Run Decision

Repository 3 will not be run locally during the current research stage.

Running it would first require:

- installing Python 3.11 alongside Python 3.12
- creating a separate environment
- installing PrivateGPT and its dependencies
- installing or configuring an OpenAI-compatible model server
- downloading suitable chat and embedding models

These installation steps are unnecessary for the current quick-review goal and would expand the scope of the research.

Repository 3 is therefore updated as:

- Level A review: completed
- Level B local run: deferred
- Level B suitability: high
- Reason for deferral: required runtime and model server are unavailable
- Future option: reconsider after all quick reviews are complete

The existing Python 3.12 installation and foundations virtual environment will remain unchanged.

## 10. Repository 4: bakrianoo/mini-rag

### Basic Information

- Repository: https://github.com/bakrianoo/mini-rag
- Default branch: `tut-017`
- License: Apache-2.0
- Review date: 2026-08-02
- Latest reviewed commit: `7705041`
- Latest commit date observed: 2025-08-15
- Project type: Educational RAG question-answering API
- Course language: Arabic
- Initial review level: Level A
- Local-run decision: Not recommended in the current environment

### Project Purpose

Mini-RAG is an educational implementation of a retrieval-augmented question-answering system.

The repository is organized as a step-by-step course. Separate branches show the project developing from a basic FastAPI application into a larger system containing:

- file uploads
- document processing
- relational data storage
- vector storage
- semantic search
- augmented answer generation
- background workers
- deployment and monitoring

The current default branch is much more complex than the repository name “mini-rag” suggests. Earlier tutorial branches represent simpler stages, while `tut-017` includes background processing and deployment infrastructure.

### Main Features

- Upload text and PDF files
- Validate uploaded file type and size
- Group files and chunks by project
- Store file records and document chunks in PostgreSQL
- Parse text with `TextLoader`
- Parse PDFs with `PyMuPDFLoader`
- Split document text into chunks
- Generate embeddings
- Store and search vectors
- Support PGVector and Qdrant providers
- Perform project-scoped semantic search
- Construct an augmented prompt from retrieved chunks
- Generate an answer through an LLM provider
- Run document processing and indexing through Celery
- Provide Docker deployment and monitoring configuration

### Technology Stack

| Category | Technology |
|---|---|
| Programming language | Python 3.10 |
| Web framework | FastAPI |
| API server | Uvicorn |
| Document processing | LangChain loaders and PyMuPDF |
| Relational database | PostgreSQL |
| Database access | SQLAlchemy and asyncpg |
| Database migrations | Alembic |
| Vector storage | PGVector or Qdrant |
| Generation provider | OpenAI by default |
| Embedding provider | Cohere by default |
| Background processing | Celery |
| Message broker | RabbitMQ |
| Task-result backend | Redis |
| Monitoring | Prometheus and Grafana |
| Deployment | Docker Compose |
| License | Apache-2.0 |

### Repository Structure

```text
mini-rag/
├── src/
│   ├── controllers/
│   │   ├── DataController.py
│   │   ├── NLPController.py
│   │   ├── ProcessController.py
│   │   └── ProjectController.py
│   ├── helpers/
│   ├── models/
│   ├── routes/
│   │   ├── base.py
│   │   ├── data.py
│   │   └── nlp.py
│   ├── stores/
│   │   ├── llm/
│   │   └── vectordb/
│   ├── tasks/
│   │   ├── data_indexing.py
│   │   ├── file_processing.py
│   │   ├── maintenance.py
│   │   └── process_workflow.py
│   ├── celery_app.py
│   ├── main.py
│   ├── requirements.txt
│   └── .env.example
├── docker/
│   ├── docker-compose.yml
│   ├── minirag/
│   ├── nginx/
│   ├── prometheus/
│   └── rabbitmq/
├── assets/
├── README.md
└── LICENSE
```

### Core Ingestion and Indexing Flow

The reviewed document flow is:

1. A client uploads a text or PDF file to a project-specific FastAPI endpoint.
2. The API validates the file type and maximum size.
3. The file is written to a project directory using a generated filename.
4. An asset record is stored in PostgreSQL.
5. A processing request starts a Celery task.
6. The processing controller loads the file using a text or PDF loader.
7. The extracted text is divided into chunks.
8. Chunk text, order, project ID, and asset ID are stored in PostgreSQL.
9. A separate indexing task loads chunks in batches.
10. The configured embedding provider generates vectors.
11. The vectors are inserted into a project-specific PGVector or Qdrant collection.

The repository also provides a chained workflow that runs document processing first and vector indexing second.

### Core Retrieval and Answer Flow

The reviewed retrieval flow is:

1. A client submits a question and project ID.
2. The question is converted into an embedding.
3. The application searches the vector collection associated with that project.
4. The most similar chunks are returned.
5. Retrieved chunk text is inserted into a prompt template.
6. The original question is appended to the prompt.
7. The configured generation provider produces the final answer.
8. The API returns the answer, constructed prompt, and chat history.

A separate search endpoint can return the retrieved text and similarity scores without generating an answer.

### Metadata and Citation Findings

The relational schema provides useful links between:

- project
- uploaded asset
- chunk
- chunk order
- chunk metadata

However, the current simple splitter creates chunks with empty metadata instead of preserving the document loader’s page and source metadata.

The answer endpoint does not return a structured citation list. It returns the generated answer, full prompt, and chat history.

Therefore, this repository demonstrates the basic retrieval and generation sequence but does not provide a citation design suitable for the planned project.

### Implementation Limitations Observed

- The accepted `overlap_size` value is not used by the current simple splitter.
- Document loader metadata is not preserved by the simple splitter.
- The final-chunk condition can add an empty chunk.
- The answer response exposes the complete constructed prompt and chat history.
- Retrieval results are not converted into structured source citations.
- Several responsibilities remain inside controllers.
- Dependency versions are older than those in Repository 3.
- The latest branch requires considerably more infrastructure than a minimal teaching example.

These findings do not make the repository useless. They show which educational patterns should be improved before using them in a production-style project.

### Running Requirements

The documented setup expects:

- Python 3.10
- Linux-oriented system packages such as PostgreSQL development libraries and a C compiler
- a separate Python environment
- PostgreSQL with PGVector
- database migrations
- OpenAI and Cohere credentials under the default configuration
- RabbitMQ and Redis for background tasks
- Docker for the complete deployment path

The full Docker Compose configuration also includes:

- FastAPI
- Celery worker
- Celery Beat
- Flower
- PostgreSQL with PGVector
- Qdrant
- RabbitMQ
- Redis
- Nginx
- Prometheus
- Grafana
- system and PostgreSQL exporters

### Designs Worth Adopting

- Separate upload, processing, indexing, search, and answer operations.
- Validate file type and size before saving an upload.
- Give projects, files, and chunks stable identifiers.
- Link chunks to their source asset and project.
- Store operational metadata separately from vector data.
- Process vector insertion in batches.
- Keep LLM and vector-store providers behind factory interfaces.
- Keep prompt templates outside route functions.
- Use database migrations instead of manually creating tables.
- Use background processing only when document workloads justify it.

### Designs Not Suitable for Our V1

The following elements are unnecessary for the planned first version:

- Celery
- RabbitMQ
- Redis
- Flower
- Nginx
- Prometheus
- Grafana
- multiple vector-store providers
- multiple LLM providers
- scheduled maintenance workers
- a separate database table for task execution history
- the complete multi-container deployment configuration

The V1 should begin with synchronous ingestion or a simple in-process background task.

### Designs That Must Be Improved for Our V1

- Preserve filename, page number, and source metadata during chunking.
- Implement chunk overlap correctly.
- Never store empty chunks.
- Return structured source citations.
- Do not expose the full internal prompt in the normal API response.
- Move business logic out of controllers into focused services.
- Use consistent exception handling and HTTP status codes.
- Add tests for upload validation, chunking, indexing, and retrieval.

### Local Run Decision

Repository 4 will not be run locally during the current research stage.

Reasons:

- the repository requires Python 3.10, while the current computer has Python 3.12
- Docker is unavailable
- PostgreSQL and PGVector are required by the default branch
- the asynchronous workflow requires RabbitMQ and Redis
- the default model configuration requires external API credentials
- the full setup is unnecessary for a Level A architectural comparison

Repository 4 is therefore recorded as:

- Level A review: completed
- Level B local run: not selected
- Architecture relevance: medium to high
- Educational relevance: high
- Production reference quality: medium
- Main value: clearly demonstrates the basic upload-to-answer RAG sequence
- Main weakness: the current branch adds excessive infrastructure while still lacking reliable metadata and citations

### One-Sentence Conclusion

> Mini-RAG clearly exposes the individual stages of a RAG pipeline and is useful as an educational V1 comparison, but its latest branch combines excessive infrastructure with chunking and citation limitations that should not be copied.

### Sources

- Repository and README: https://github.com/bakrianoo/mini-rag
- License: https://github.com/bakrianoo/mini-rag/blob/tut-017/LICENSE
- Dependencies: https://github.com/bakrianoo/mini-rag/blob/tut-017/src/requirements.txt
- FastAPI entry point: https://github.com/bakrianoo/mini-rag/blob/tut-017/src/main.py
- Upload and processing routes: https://github.com/bakrianoo/mini-rag/blob/tut-017/src/routes/data.py
- Retrieval and answer routes: https://github.com/bakrianoo/mini-rag/blob/tut-017/src/routes/nlp.py
- Document processing controller: https://github.com/bakrianoo/mini-rag/blob/tut-017/src/controllers/ProcessController.py
- Retrieval controller: https://github.com/bakrianoo/mini-rag/blob/tut-017/src/controllers/NLPController.py
- File-processing task: https://github.com/bakrianoo/mini-rag/blob/tut-017/src/tasks/file_processing.py
- Indexing task: https://github.com/bakrianoo/mini-rag/blob/tut-017/src/tasks/data_indexing.py
- Docker Compose: https://github.com/bakrianoo/mini-rag/blob/tut-017/docker/docker-compose.yml
- Reviewed commit: https://github.com/bakrianoo/mini-rag/commit/77050419ad3dd749702fdbea71e6181e376afcd3

## 11. Cross-Repository Comparison and Reference Selection

### Comparison Summary

| Repository | FastAPI | V1 Scope Similarity | Ingestion and Retrieval | Metadata and Citations | Architecture Value | Complexity Risk | Local Run |
|---|---|---|---|---|---|---|---|
| `danny-avila/rag_api` | Yes | High | Strong | Strong file-scoped metadata; no final answer workflow | High | Medium | Deferred |
| `infiniflow/ragflow` | No, uses Quart | Low | Very strong | Enterprise-level | High for large-system boundaries | Very high | Not selected |
| `zylon-ai/private-gpt` | Yes | Medium | Very strong | Strong structured sources and citations | Very high | Very high | Deferred |
| `bakrianoo/mini-rag` | Yes | Medium | Basic but clear | Weak citation and metadata preservation | Medium | High on latest branch | Not selected |

### Repository 1: danny-avila/rag_api

Strongest qualities:

- directly focuses on document ingestion and vector retrieval
- uses FastAPI
- separates routing, services, embeddings, document processing, and vector storage
- supports file-scoped retrieval
- allows an external application to own file metadata
- does not attempt to implement an entire AI platform
- is close to the intended backend scope of our V1

Main limitations:

- does not contain the final LLM answer-generation workflow
- supports more providers and storage options than our V1 requires
- normally expects Docker and external services
- contains overlapping ingestion options that should be simplified

Selection role:

> Main architecture reference and Level C static architecture-analysis target.

### Repository 2: infiniflow/ragflow

Strongest qualities:

- demonstrates enterprise document-processing architecture
- has mature service boundaries
- supports complex parsing and retrieval
- shows production deployment and operational concerns
- demonstrates what a large knowledge platform eventually requires

Main limitations:

- uses Quart instead of FastAPI
- requires substantial infrastructure and hardware
- contains many services and components unrelated to the first version
- cannot be explained or implemented within the planned V1 scope

Selection role:

> Enterprise boundary reference used to identify features that must be deferred.

### Repository 3: zylon-ai/private-gpt

Strongest qualities:

- uses FastAPI
- has strong separation between routes, services, components, and workflows
- supports structured ingestion inputs
- preserves collection, artifact, file, and model metadata
- supports metadata-filtered retrieval
- returns source blocks suitable for citations
- provides centralized lifecycle, configuration, and error-handling patterns

Main limitations:

- has grown into a complete private AI application platform
- includes agents, skills, tools, MCP, structured data, and other advanced features
- uses a more complex workflow and dependency-injection system than our V1 needs
- cannot currently be run because Python 3.11 and a compatible model server are unavailable

Selection role:

> Secondary architecture reference for module boundaries, metadata, citations, configuration, and error handling.

### Repository 4: bakrianoo/mini-rag

Strongest qualities:

- clearly shows the sequence from upload to answer generation
- uses FastAPI
- separates upload, processing, indexing, search, and answer endpoints
- links projects, assets, and chunks
- demonstrates provider factories and batched vector indexing
- is useful for learning the basic RAG data flow

Main limitations:

- the current branch includes excessive deployment and worker infrastructure
- chunk overlap is not implemented correctly
- source metadata is not preserved by the simple splitter
- structured citations are missing
- the answer endpoint exposes the complete internal prompt
- it is an educational repository rather than the strongest production reference

Selection role:

> Educational reference and source of implementation mistakes that our V1 should avoid.

### Main Architecture Reference Decision

`danny-avila/rag_api` is selected as the main architecture reference.

Reasons:

1. Its purpose is closest to the planned Enterprise Knowledge Assistant backend.
2. It concentrates on the two most important V1 responsibilities:
   - document ingestion
   - scoped vector retrieval
3. It uses FastAPI.
4. Its `file_id` filtering pattern is suitable for connecting chunks to uploaded documents.
5. Its scope is smaller and easier to explain than RAGFlow or PrivateGPT.
6. Its design can be simplified without changing the core architecture.
7. The missing answer-generation layer can be designed using selected citation patterns from PrivateGPT.

Selecting this repository does not mean copying its implementation. It means using it to study:

- module boundaries
- ingestion request flow
- document-processing flow
- vector-storage boundaries
- retrieval filtering
- configuration
- dependency direction
- errors
- logging
- testing

### Secondary Architecture Reference Decision

`zylon-ai/private-gpt` is selected as the secondary architecture reference.

The following patterns will be studied and selectively adopted:

- keeping FastAPI routers thin
- separating API services from reusable components
- structured collection and artifact metadata
- source blocks and citations
- centralized application startup and shutdown
- provider configuration
- centralized exception handling

Its agent, tool, workflow, and platform features will not be included in V1.

### V1 Architecture Direction Emerging from the Research

The planned V1 should contain the following main modules:

```text
app/
├── api/
│   ├── documents.py
│   ├── retrieval.py
│   └── health.py
├── services/
│   ├── ingestion_service.py
│   ├── retrieval_service.py
│   └── answer_service.py
├── document_processing/
│   ├── loaders.py
│   └── chunker.py
├── embeddings/
│   └── embedding_provider.py
├── vector_store/
│   └── vector_store.py
├── models/
│   ├── document.py
│   ├── chunk.py
│   └── api_schemas.py
├── core/
│   ├── config.py
│   ├── errors.py
│   └── logging.py
└── main.py
```

The initial version should support:

- FastAPI
- text and PDF uploads
- synchronous ingestion
- one embedding provider
- one vector store
- document and chunk identifiers
- filename and page metadata
- document-scoped retrieval
- generated answers
- structured source citations
- health checks
- basic logging
- a small evaluation set

The initial version should not include:

- Celery
- RabbitMQ
- Redis
- multiple vector databases
- multiple model providers
- agents
- tools
- MCP
- text-to-SQL
- multimodal processing
- enterprise authentication
- multi-tenant infrastructure
- distributed workers
- monitoring dashboards

### Local Run Review Outcome

No repository was run locally during the quick-review phase because the required environments were not practically available:

- Docker is unavailable.
- Python 3.10 and Python 3.11 are unavailable.
- The installed Python version is 3.12.
- Ollama is unavailable.
- Several repositories require databases, workers, model servers, or external credentials.

The local-run deferrals do not prevent static architecture analysis. Source code, configuration, dependencies, routes, and documented workflows provide enough evidence to select the Level C reference.

### Research Status After Comparison

- Four Level A repository reviews: completed
- Main Level C reference selected: `danny-avila/rag_api`
- Secondary architecture reference selected: `zylon-ai/private-gpt`
- Local functional reviews: deferred where impractical
- Enterprise complexity boundary identified: completed
- Initial V1 architecture direction: established
- Next activity: deeper static architecture analysis of `danny-avila/rag_api`


## 12. Final Research Status and Corrections

- Original research date: 2026-08-02
- Final documentation update: 2026-08-03

This section supersedes earlier pending table entries, placeholder repository names, and outdated commit observations.

### Final Repository Summary

| No. | Repository | Completed Review | Main Purpose | Main Stack | Local Run | Relevance | Final Status |
|---:|---|---|---|---|---|---|---|
| 1 | `danny-avila/rag_api` | Level A and Level C | ID-based document ingestion and retrieval API | FastAPI, LangChain, PGVector or Atlas MongoDB | Deferred | High | Main architecture reference |
| 2 | `infiniflow/ragflow` | Level A | Enterprise RAG and document-understanding platform | Quart, React, Elasticsearch, MySQL, Redis, MinIO | Not selected | High for enterprise boundaries | Quick review completed |
| 3 | `zylon-ai/private-gpt` | Level A | Private AI API platform with RAG and citations | FastAPI, LlamaIndex, Qdrant | Deferred | High | Secondary architecture reference |
| 4 | `bakrianoo/mini-rag` | Level A | Educational upload-to-answer RAG pipeline | FastAPI, LangChain, PostgreSQL, PGVector, Celery | Not selected | Medium to high | Educational reference |

Rows 5 and 6 from the original planning table are no longer required. The research reached sufficient evidence after four repositories.

### Repository 1 Commit Correction

The initial Repository 1 review recorded `12a4469` as the latest observed commit.

The later Level C review found a newer commit on the current `main` branch:

- Correct latest reviewed commit: `4985b37`
- Commit date: 2026-07-31
- Main change: safe parallel ingestion consumers and rollback improvements

The Level C analysis and final architecture decisions use commit `4985b37`.

Source:

- https://github.com/danny-avila/rag_api/commit/4985b37b8b5d4519d68eceedfef1e63624012f9d

### Local Run Outcome

Local functional reviews were deferred because they were not practical in the available environment.

Observed environment:

- Docker: unavailable
- Installed Python: 3.12
- Python 3.10: unavailable
- Python 3.11: unavailable
- Ollama: unavailable

Repository-specific consequences:

- `danny-avila/rag_api`: Docker or a separately configured vector database would be required.
- `infiniflow/ragflow`: Docker and substantial system resources would be required.
- `zylon-ai/private-gpt`: Python 3.11 and an OpenAI-compatible model server would be required.
- `bakrianoo/mini-rag`: Python 3.10, PostgreSQL, worker services, and model credentials would be required.

No repository was installed into the existing foundations virtual environment.

### Final Reference Selection

- Main architecture reference: `danny-avila/rag_api`
- Secondary architecture reference: `zylon-ai/private-gpt`
- Enterprise complexity boundary: `infiniflow/ragflow`
- Educational and counterexample reference: `bakrianoo/mini-rag`

### Research Completion Check

- Four relevant repositories received quick reviews: completed
- Main reference selected: completed
- Main reference received deeper static architecture analysis: completed
- README, dependencies, routes, configuration, core flows, and tests were reviewed: completed
- Important findings were recorded with source links: completed
- Adopted and rejected patterns were identified: completed
- Local runs were considered and deferred where impractical: completed
- V1 architecture and scope were justified: completed
- Architecture decisions were recorded in `architecture_log.md`: completed

### Final Research Conclusion

The research phase is complete.

The selected V1 is a modular FastAPI application using:

- synchronous TXT and PDF ingestion
- SQLite document records
- locally persisted Qdrant vectors
- explicit document and chunk metadata
- document-scoped retrieval
- one embedding provider
- one answer-generation provider
- structured source citations
- typed errors
- privacy-safe logging
- focused tests and a small evaluation dataset

The next phase is implementation planning and creation of the dependency-light project skeleton.