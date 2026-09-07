"""Versioned bounded-routing answer endpoint."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from starlette.concurrency import run_in_threadpool

from app.api.dependencies import get_routed_answer_service
from app.schemas.routed_answers import RoutedAnswerRequest, RoutedAnswerResponse
from app.services.routed_answer_service import RoutedAnswerService

router = APIRouter(prefix="/answers", tags=["routed-answers"])


@router.post("", response_model=RoutedAnswerResponse)
async def create_routed_answer(
    payload: RoutedAnswerRequest,
    service: Annotated[RoutedAnswerService, Depends(get_routed_answer_service)],
) -> RoutedAnswerResponse:
    result = await run_in_threadpool(
        service.answer,
        payload.question,
        payload.document_ids,
        payload.top_k,
        payload.score_threshold,
    )
    return RoutedAnswerResponse.from_domain(result)
