"""Pydantic schemas for historical model performance reporting."""

from datetime import datetime

from pydantic import BaseModel, Field


class PerformanceFilters(BaseModel):
    model_id: str | None = None
    task_type: str | None = None
    since: datetime | None = None
    until: datetime | None = None


class OutcomeCounts(BaseModel):
    success: int = 0
    quality_failure: int = 0
    retryable_failure: int = 0
    non_retryable_failure: int = 0
    timeout: int = 0


class ModelPerformance(BaseModel):
    model_id: str
    provider: str
    request_count: int = Field(description="Generation attempts sent to this model (initial, fallback and escalation).")
    success_count: int = Field(description="Attempts where the provider returned a response, including quality failures.")
    success_rate: float = Field(description="success_count / request_count.")
    quality_failure_rate: float = Field(description="Share of attempts whose response scored below the escalation threshold.")
    fallback_rate: float = Field(description="Share of attempts after which the gateway moved on to another model.")
    average_latency_ms: float | None = Field(description="Mean latency of successful attempts only; None if there were none.")
    average_estimated_cost: float | None = Field(
        description="Mean cost from token usage x registry pricing, over attempts that returned a response."
    )
    average_quality_score: float | None = Field(description="Mean judge score over scored attempts; None if none were scored.")
    outcomes: OutcomeCounts
    first_seen: datetime
    last_seen: datetime


class PerformanceReport(BaseModel):
    filters: PerformanceFilters
    models: list[ModelPerformance] = Field(default_factory=list)
