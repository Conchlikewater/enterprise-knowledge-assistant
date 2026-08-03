"""Document upload and lifecycle endpoints."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Response, UploadFile, status
from starlette.concurrency import run_in_threadpool

from app.api.dependencies import get_document_service, get_ingestion_service
from app.schemas.documents import DocumentListResponse, DocumentResponse
from app.services.document_service import DocumentService
from app.services.ingestion_service import IngestionService

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: Annotated[UploadFile, File(description="UTF-8 TXT or text-based PDF")],
    service: Annotated[IngestionService, Depends(get_ingestion_service)],
) -> DocumentResponse:
    try:
        document = await run_in_threadpool(
            service.ingest,
            file.file,
            file.filename or "",
            file.content_type or "",
        )
        return DocumentResponse.from_domain(document)
    finally:
        await file.close()


@router.get("", response_model=DocumentListResponse)
def list_documents(
    service: Annotated[DocumentService, Depends(get_document_service)],
) -> DocumentListResponse:
    documents = [
        DocumentResponse.from_domain(document) for document in service.list_documents()
    ]
    return DocumentListResponse(documents=documents, count=len(documents))


@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(
    document_id: UUID,
    service: Annotated[DocumentService, Depends(get_document_service)],
) -> DocumentResponse:
    return DocumentResponse.from_domain(service.get_document(document_id))


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: UUID,
    service: Annotated[DocumentService, Depends(get_document_service)],
) -> Response:
    service.delete_document(document_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
