"""FastAPI application factory and ASGI entry point."""

from __future__ import annotations

from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request

from app.api.routers.answers import router as answers_router
from app.api.routers.documents import router as documents_router
from app.api.routers.health import router as health_router
from app.api.routers.ingestion_jobs import router as ingestion_jobs_router
from app.api.routers.retrieval import router as retrieval_router
from app.api.routers.routed_answers import router as routed_answers_router
from app.core.config import Settings
from app.core.error_handlers import register_error_handlers
from app.core.logging import configure_logging
from app.providers.embedding_provider import EmbeddingProvider
from app.providers.llm_provider import LLMProvider
from app.providers.llm_provider_factory import create_llm_provider
from app.providers.openai_embedding_provider import OpenAIEmbeddingProvider
from app.services.answer_service import AnswerService
from app.services.async_ingestion_service import AsyncIngestionService
from app.services.document_service import DocumentService
from app.services.ingestion_service import IngestionService
from app.services.retrieval_service import RetrievalService
from app.services.routed_answer_service import RoutedAnswerService
from app.storage.document_repository import DocumentRepository
from app.storage.ingestion_job_repository import IngestionJobRepository
from app.storage.qdrant_vector_store import QdrantVectorStore
from app.storage.sqlite_document_repository import SQLiteDocumentRepository
from app.storage.vector_store import VectorStore


def create_app(
    settings: Settings | None = None,
    document_repository: DocumentRepository | None = None,
    ingestion_job_repository: IngestionJobRepository | None = None,
    vector_store: VectorStore | None = None,
    embedding_provider: EmbeddingProvider | None = None,
    llm_provider: LLMProvider | None = None,
) -> FastAPI:
    resolved_settings = settings or Settings.from_env()
    configure_logging(resolved_settings.log_level)
    resolved_repository = document_repository or SQLiteDocumentRepository(
        resolved_settings.sqlite_path,
        busy_timeout_ms=resolved_settings.sqlite_busy_timeout_ms,
    )
    resolved_job_repository = ingestion_job_repository
    if resolved_job_repository is None and isinstance(
        resolved_repository,
        IngestionJobRepository,
    ):
        resolved_job_repository = resolved_repository
    resolved_vector_store = vector_store or QdrantVectorStore(
        storage_path=(
            None
            if resolved_settings.qdrant_url is not None
            else resolved_settings.qdrant_path
        ),
        collection_name=resolved_settings.qdrant_collection,
        vector_size=resolved_settings.embedding_dimensions,
        url=resolved_settings.qdrant_url,
        api_key=resolved_settings.qdrant_api_key,
        timeout_seconds=resolved_settings.qdrant_timeout_seconds,
    )

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        resolved_repository.initialize()
        if (
            resolved_job_repository is not None
            and resolved_job_repository is not resolved_repository
        ):
            resolved_job_repository.initialize()
        resolved_vector_store.initialize()
        runtime_provider = embedding_provider
        runtime_llm_provider = llm_provider
        try:
            if (
                runtime_provider is None
                and resolved_settings.openai_api_key is not None
            ):
                runtime_provider = OpenAIEmbeddingProvider(
                    api_key=resolved_settings.openai_api_key,
                    model=resolved_settings.embedding_model,
                    dimensions=resolved_settings.embedding_dimensions,
                    batch_size=resolved_settings.embedding_batch_size,
                    timeout_seconds=resolved_settings.openai_timeout_seconds,
                )
            if runtime_llm_provider is None:
                runtime_llm_provider = create_llm_provider(resolved_settings)

            application.state.document_repository = resolved_repository
            application.state.ingestion_job_repository = resolved_job_repository
            application.state.vector_store = resolved_vector_store
            application.state.embedding_provider = runtime_provider
            application.state.llm_provider = runtime_llm_provider
            application.state.document_service = DocumentService(
                document_repository=resolved_repository,
                vector_store=resolved_vector_store,
                upload_dir=resolved_settings.upload_dir,
            )
            application.state.async_ingestion_service = (
                AsyncIngestionService(
                    ingestion_job_repository=resolved_job_repository,
                    upload_dir=resolved_settings.upload_dir,
                    max_upload_bytes=resolved_settings.max_upload_bytes,
                )
                if resolved_job_repository is not None
                else None
            )
            application.state.ingestion_service = (
                IngestionService(
                    document_repository=resolved_repository,
                    vector_store=resolved_vector_store,
                    embedding_provider=runtime_provider,
                    upload_dir=resolved_settings.upload_dir,
                    max_upload_bytes=resolved_settings.max_upload_bytes,
                    chunk_size=resolved_settings.chunk_size,
                    chunk_overlap=resolved_settings.chunk_overlap,
                )
                if runtime_provider is not None
                else None
            )
            runtime_retrieval_service = (
                RetrievalService(
                    document_repository=resolved_repository,
                    vector_store=resolved_vector_store,
                    embedding_provider=runtime_provider,
                )
                if runtime_provider is not None
                else None
            )
            application.state.retrieval_service = runtime_retrieval_service
            runtime_answer_service = (
                AnswerService(
                    retrieval_service=runtime_retrieval_service,
                    llm_provider=runtime_llm_provider,
                )
                if runtime_retrieval_service is not None
                and runtime_llm_provider is not None
                else None
            )
            application.state.answer_service = runtime_answer_service
            application.state.routed_answer_service = RoutedAnswerService(
                retrieval_service=runtime_retrieval_service,
                answer_service=runtime_answer_service,
            )
            yield
        finally:
            try:
                try:
                    if runtime_llm_provider is not None:
                        runtime_llm_provider.close()
                finally:
                    if runtime_provider is not None:
                        runtime_provider.close()
            finally:
                resolved_vector_store.close()

    application = FastAPI(
        title=resolved_settings.app_name,
        version=resolved_settings.app_version,
        description="Local, document-scoped RAG API.",
        lifespan=lifespan,
    )
    application.state.settings = resolved_settings

    @application.middleware("http")
    async def attach_request_id(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    register_error_handlers(application)
    application.include_router(health_router)
    application.include_router(
        documents_router,
        prefix=resolved_settings.api_v1_prefix,
    )
    application.include_router(
        retrieval_router,
        prefix=resolved_settings.api_v1_prefix,
    )
    application.include_router(
        answers_router,
        prefix=resolved_settings.api_v1_prefix,
    )
    application.include_router(
        ingestion_jobs_router,
        prefix=resolved_settings.api_v2_prefix,
    )
    application.include_router(
        routed_answers_router,
        prefix=resolved_settings.api_v2_prefix,
    )
    return application


app = create_app()
