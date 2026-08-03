"""Service health endpoint."""

from fastapi import APIRouter, Request

from app.core.config import Settings
from app.core.exceptions import (
    DocumentRepositoryError,
    ProviderConfigurationError,
    VectorStoreError,
)
from app.providers.embedding_provider import EmbeddingProvider
from app.providers.llm_provider import LLMProvider
from app.schemas.health import HealthResponse
from app.storage.document_repository import DocumentRepository
from app.storage.vector_store import VectorStore

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    settings: Settings = request.app.state.settings
    repository: DocumentRepository = request.app.state.document_repository
    vector_store: VectorStore = request.app.state.vector_store
    embedding_provider: EmbeddingProvider | None = request.app.state.embedding_provider
    llm_provider: LLMProvider | None = request.app.state.llm_provider
    if not repository.health():
        raise DocumentRepositoryError()
    if not vector_store.health():
        raise VectorStoreError()
    if embedding_provider is None:
        raise ProviderConfigurationError()
    if llm_provider is None:
        raise ProviderConfigurationError()
    return HealthResponse(
        service=settings.app_name,
        version=settings.app_version,
        components={
            "application": "ok",
            "document_repository": "ok",
            "vector_store": "ok",
            "embedding_provider": "configured",
            "llm_provider": "configured",
        },
    )
