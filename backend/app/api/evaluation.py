"""Evaluation API endpoints."""

from fastapi import APIRouter

from app.evaluation.judge import get_judge
from app.schemas.evaluation import EvaluateRequest, EvaluateResponse

router = APIRouter(prefix="/api/evaluate", tags=["evaluation"])


@router.post("", response_model=EvaluateResponse)
async def evaluate_response(request: EvaluateRequest) -> EvaluateResponse:
    judge = get_judge()
    scores = await judge.evaluate(request.prompt, request.response)
    return EvaluateResponse(scores=scores)
