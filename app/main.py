"""FastAPI application factory and ASGI entry point."""

from __future__ import annotations

from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request

from app.api.routers.documents import router as documents_router
from app.api.routers.health import router as health_router
from app.api.routers.retrieval import router as retrieval_router
from app.core.config import Settings
from app.core.error_handlers import register_error_handlers
from app.providers.embedding_provider import EmbeddingProvider
from app.providers.openai_embedding_provider import OpenAIEmbeddingProvider
from app.services.document_service import DocumentService
from app.services.ingestion_service import IngestionService
from app.services.retrieval_service import RetrievalService
from app.storage.document_repository import DocumentRepository
from app.storage.qdrant_vector_store import QdrantVectorStore
from app.storage.sqlite_document_repository import SQLiteDocumentRepository
from app.storage.vector_store import VectorStore


def create_app(
    settings: Settings | None = None,
    document_repository: DocumentRepository | None = None,
    vector_store: VectorStore | None = None,
    embedding_provider: EmbeddingProvider | None = None,
) -> FastAPI:
    resolved_settings = settings or Settings.from_env()
    resolved_repository = document_repository or SQLiteDocumentRepository(
        resolved_settings.sqlite_path
    )
    resolved_vector_store = vector_store or QdrantVectorStore(
        storage_path=resolved_settings.qdrant_path,
        collection_name=resolved_settings.qdrant_collection,
        vector_size=resolved_settings.embedding_dimensions,
    )

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        resolved_repository.initialize()
        resolved_vector_store.initialize()
        runtime_provider = embedding_provider
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

            application.state.document_repository = resolved_repository
            application.state.vector_store = resolved_vector_store
            application.state.embedding_provider = runtime_provider
            application.state.document_service = DocumentService(
                document_repository=resolved_repository,
                vector_store=resolved_vector_store,
                upload_dir=resolved_settings.upload_dir,
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
            application.state.retrieval_service = (
                RetrievalService(
                    document_repository=resolved_repository,
                    vector_store=resolved_vector_store,
                    embedding_provider=runtime_provider,
                )
                if runtime_provider is not None
                else None
            )
            yield
        finally:
            try:
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
    return application


app = create_app()
