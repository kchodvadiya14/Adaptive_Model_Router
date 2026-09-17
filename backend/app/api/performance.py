"""Historical model performance API (reporting only; does not affect routing)."""

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, status

from app.schemas.performance import PerformanceFilters, PerformanceReport
from app.services.performance import as_utc, get_model_performance

router = APIRouter(prefix="/api/performance", tags=["performance"])


@router.get("/models", response_model=PerformanceReport)
def get_models_performance(
    model_id: str | None = Query(default=None),
    task_type: str | None = Query(default=None),
    since: datetime | None = Query(default=None, description="ISO 8601; inclusive. Naive values are UTC."),
    until: datetime | None = Query(default=None, description="ISO 8601; inclusive. Naive values are UTC."),
) -> PerformanceReport:
    """Per-model request count, success rate, latency, cost, quality and fallback rate,
    computed from every recorded generation attempt."""
    since_utc, until_utc = as_utc(since), as_utc(until)
    if since_utc and until_utc and since_utc > until_utc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="since must not be after until.")
    return get_model_performance(
        PerformanceFilters(model_id=model_id, task_type=task_type, since=since_utc, until=until_utc)
    )
