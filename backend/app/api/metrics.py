"""Metrics API endpoints."""

from fastapi import APIRouter

from app.db.repository import get_metrics_summary
from app.schemas.evaluation import MetricsSummary

router = APIRouter(prefix="/api/metrics", tags=["metrics"])


@router.get("", response_model=MetricsSummary)
def read_metrics() -> MetricsSummary:
    return get_metrics_summary()
