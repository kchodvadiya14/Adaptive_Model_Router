"""Historical model performance reporting, plus quality calibration of the model registry."""

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, status

from app.schemas.performance import PerformanceFilters, PerformanceReport
from app.services.calibration import (
    DEFAULT_MIN_SAMPLES,
    DEFAULT_PRIOR_WEIGHT,
    CalibrationReport,
    calibrate,
)
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


def _calibration(min_samples: int, prior_weight: int, since: datetime | None, apply: bool) -> CalibrationReport:
    return calibrate(min_samples=min_samples, prior_weight=prior_weight, since=as_utc(since), apply=apply)


@router.get("/calibration", response_model=CalibrationReport)
def preview_calibration(
    min_samples: int = Query(default=DEFAULT_MIN_SAMPLES, ge=1),
    prior_weight: int = Query(default=DEFAULT_PRIOR_WEIGHT, ge=0),
    since: datetime | None = Query(default=None, description="Only use outcomes recorded at or after this time."),
) -> CalibrationReport:
    """What each model's registry quality_score would become if calibrated against judged
    outcomes. Changes nothing."""
    return _calibration(min_samples, prior_weight, since, apply=False)


@router.post("/calibration/apply", response_model=CalibrationReport)
def apply_calibration(
    min_samples: int = Query(default=DEFAULT_MIN_SAMPLES, ge=1),
    prior_weight: int = Query(default=DEFAULT_PRIOR_WEIGHT, ge=0),
    since: datetime | None = Query(default=None, description="Only use outcomes recorded at or after this time."),
) -> CalibrationReport:
    """Write calibrated quality_score values to the registry for every model with at least
    min_samples judged outcomes. Re-applying over the same window double-counts it; pass
    `since` to use only newer outcomes."""
    return _calibration(min_samples, prior_weight, since, apply=True)
