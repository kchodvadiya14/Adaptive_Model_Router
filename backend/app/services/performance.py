"""Historical per-model performance, aggregated from recorded model outcomes.

Reporting only: nothing here influences routing decisions.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.db import outcome_repository
from app.schemas.performance import ModelPerformance, OutcomeCounts, PerformanceFilters, PerformanceReport


def as_utc(moment: datetime | None) -> datetime | None:
    """Naive datetimes are taken as UTC."""
    if moment is None:
        return None
    return moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment.astimezone(UTC)


def _rate(part: int, whole: int) -> float:
    return round(part / whole, 4) if whole else 0.0


def _rounded(value: float | None, digits: int) -> float | None:
    return round(value, digits) if value is not None else None


def get_model_performance(filters: PerformanceFilters) -> PerformanceReport:
    normalized = PerformanceFilters(
        model_id=filters.model_id,
        task_type=filters.task_type,
        since=as_utc(filters.since),
        until=as_utc(filters.until),
    )
    rows = outcome_repository.aggregate_by_model(
        model_id=normalized.model_id,
        task_type=normalized.task_type,
        since=normalized.since,
        until=normalized.until,
    )

    models = []
    for row in rows:
        total = row["request_count"]
        outcomes = OutcomeCounts(**{name: row[f"outcome_{name}"] or 0 for name in outcome_repository.ALL_OUTCOMES})
        models.append(
            ModelPerformance(
                model_id=row["model_id"],
                provider=row["provider"],
                request_count=total,
                success_count=row["success_count"] or 0,
                success_rate=_rate(row["success_count"] or 0, total),
                quality_failure_rate=_rate(outcomes.quality_failure, total),
                fallback_rate=_rate(row["fallback_count"] or 0, total),
                average_latency_ms=_rounded(row["average_latency_ms"], 2),
                average_estimated_cost=_rounded(row["average_estimated_cost"], 8),
                average_quality_score=_rounded(row["average_quality_score"], 4),
                outcomes=outcomes,
                first_seen=datetime.fromtimestamp(row["first_recorded_at"], tz=UTC),
                last_seen=datetime.fromtimestamp(row["last_recorded_at"], tz=UTC),
            )
        )
    return PerformanceReport(filters=normalized, models=models)
