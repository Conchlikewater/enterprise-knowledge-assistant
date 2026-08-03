"""Document-scoped semantic search endpoint."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from starlette.concurrency import run_in_threadpool

from app.api.dependencies import get_retrieval_service
from app.schemas.retrieval import (
    RetrievalResultResponse,
    SearchRequest,
    SearchResponse,
)
from app.services.retrieval_service import RetrievalService

router = APIRouter(tags=["retrieval"])


@router.post("/search", response_model=SearchResponse)
async def search_documents(
    request: SearchRequest,
    service: Annotated[RetrievalService, Depends(get_retrieval_service)],
) -> SearchResponse:
    results = await run_in_threadpool(
        service.search,
        request.query,
        request.document_ids,
        request.top_k,
        request.score_threshold,
    )
    response_results = [
        RetrievalResultResponse.from_domain(result) for result in results
    ]
    return SearchResponse(
        results=response_results,
        count=len(response_results),
        searched_document_ids=request.document_ids,
    )
