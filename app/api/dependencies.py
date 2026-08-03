"""Small FastAPI dependency functions for application services."""

from fastapi import Request

from app.core.exceptions import ProviderConfigurationError
from app.services.answer_service import AnswerService
from app.services.document_service import DocumentService
from app.services.ingestion_service import IngestionService
from app.services.retrieval_service import RetrievalService


def get_document_service(request: Request) -> DocumentService:
    return request.app.state.document_service


def get_ingestion_service(request: Request) -> IngestionService:
    service: IngestionService | None = request.app.state.ingestion_service
    if service is None:
        raise ProviderConfigurationError()
    return service


def get_retrieval_service(request: Request) -> RetrievalService:
    service: RetrievalService | None = request.app.state.retrieval_service
    if service is None:
        raise ProviderConfigurationError()
    return service


def get_answer_service(request: Request) -> AnswerService:
    service: AnswerService | None = request.app.state.answer_service
    if service is None:
        raise ProviderConfigurationError()
    return service
