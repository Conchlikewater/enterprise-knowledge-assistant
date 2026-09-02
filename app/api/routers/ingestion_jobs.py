"""R23 asynchronous intake and Job status endpoints."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, UploadFile, status
from starlette.concurrency import run_in_threadpool

from app.api.dependencies import get_async_ingestion_service
from app.schemas.ingestion_jobs import (
    AsyncDocumentAcceptedResponse,
    IngestionJobResponse,
)
from app.services.async_ingestion_service import AsyncIngestionService

router = APIRouter(tags=["async-ingestion"])


@router.post(
    "/documents",
    response_model=AsyncDocumentAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def submit_document(
    file: Annotated[UploadFile, File(description="UTF-8 TXT or text-based PDF")],
    service: Annotated[AsyncIngestionService, Depends(get_async_ingestion_service)],
) -> AsyncDocumentAcceptedResponse:
    try:
        document, job = await run_in_threadpool(
            service.submit,
            file.file,
            file.filename or "",
            file.content_type or "",
        )
        return AsyncDocumentAcceptedResponse.from_domain(document, job)
    finally:
        await file.close()


@router.get("/jobs/{job_id}", response_model=IngestionJobResponse)
def get_ingestion_job(
    job_id: UUID,
    service: Annotated[AsyncIngestionService, Depends(get_async_ingestion_service)],
) -> IngestionJobResponse:
    return IngestionJobResponse.from_domain(service.get_job(job_id))
