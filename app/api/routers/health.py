"""Service health endpoint."""

from fastapi import APIRouter, Request

from app.core.config import Settings
from app.core.exceptions import DocumentRepositoryError
from app.schemas.health import HealthResponse
from app.storage.document_repository import DocumentRepository

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    settings: Settings = request.app.state.settings
    repository: DocumentRepository = request.app.state.document_repository
    if not repository.health():
        raise DocumentRepositoryError()
    return HealthResponse(
        service=settings.app_name,
        version=settings.app_version,
        components={"application": "ok", "document_repository": "ok"},
    )
