"""Pydantic schemas for routing API."""

from typing import Any

from pydantic import BaseModel, Field


class RouteRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=32000)


class TierQualityEstimate(BaseModel):
    tier: str
    model_id: str | None
    expected_quality: float
    estimated_cost: float
    meets_quality_floor: bool


class RoutingDecision(BaseModel):
    selected_model: str
    model_tier: str
    confidence: float = Field(ge=0, le=1)
    difficulty: float = Field(ge=0, le=1)
    task_type: str
    reason: str
    estimated_cost: float = Field(ge=0)
    estimated_quality: float = Field(ge=0, le=1)
    strong_model_baseline_cost: float = Field(ge=0)
    cost_saved_vs_strong: float = Field(ge=0)
    explanation: list[str] = Field(default_factory=list)
    tier_qualities: list[TierQualityEstimate] = Field(default_factory=list)
    features: dict[str, Any] = Field(default_factory=dict)


class RouteConfigOverride(BaseModel):
    quality_floor: float | None = Field(default=None, ge=0, le=1)
    cost_priority: float | None = Field(default=None, ge=0, le=1)
    latency_priority: float | None = Field(default=None, ge=0, le=1)


class RouteRequestWithConfig(RouteRequest):
    configuration: RouteConfigOverride | None = None
