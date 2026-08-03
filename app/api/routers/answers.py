"""Evidence-grounded answer endpoint."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from starlette.concurrency import run_in_threadpool

from app.api.dependencies import get_answer_service
from app.schemas.answers import AnswerRequest, AnswerResponse
from app.services.answer_service import AnswerService

router = APIRouter(tags=["answers"])


@router.post("/answers", response_model=AnswerResponse)
async def answer_question(
    request: AnswerRequest,
    service: Annotated[AnswerService, Depends(get_answer_service)],
) -> AnswerResponse:
    result = await run_in_threadpool(
        service.answer,
        request.question,
        request.document_ids,
        request.top_k,
        request.score_threshold,
    )
    return AnswerResponse.from_domain(result)
