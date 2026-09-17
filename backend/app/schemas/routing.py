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
    preferred_model: str | None = Field(default=None, description="The preferred_model the caller asked for, if any.")
    preferred_model_honored: bool | None = Field(
        default=None,
        description="Whether preferred_model was selected. None when no preference was given.",
    )


class RouteConfigOverride(BaseModel):
    quality_floor: float | None = Field(default=None, ge=0, le=1)
    cost_priority: float | None = Field(default=None, ge=0, le=1)
    latency_priority: float | None = Field(default=None, ge=0, le=1)


class RouteRequestWithConfig(RouteRequest):
    configuration: RouteConfigOverride | None = None
    preferred_model: str | None = Field(default=None, description="Model to prefer if it passes every eligibility check.")
    max_cost: float | None = Field(default=None, ge=0, description="Maximum estimated cost per request (USD).")
    max_latency_ms: float | None = Field(default=None, ge=0, description="Maximum average model latency (ms).")

    def routing_configuration(self) -> dict[str, Any] | None:
        configuration = self.configuration.model_dump(exclude_none=True) if self.configuration else {}
        if self.preferred_model:
            configuration["preferred_model"] = self.preferred_model
        if self.max_cost is not None:
            configuration["max_cost"] = self.max_cost
        if self.max_latency_ms is not None:
            configuration["max_latency_ms"] = self.max_latency_ms
        return configuration or None
