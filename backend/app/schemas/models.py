"""Pydantic schemas for model registry and API responses."""

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class ModelTier(str, Enum):
    SMALL = "small"
    MEDIUM = "medium"
    STRONG = "strong"


class ModelType(str, Enum):
    API = "api"
    OPEN_SOURCE = "open_source"
    LOCAL = "local"


class ModelCapability(str, Enum):
    CODING = "coding"
    REASONING = "reasoning"
    SUMMARIZATION = "summarization"
    CREATIVE_WRITING = "creative_writing"
    TRANSLATION = "translation"
    EXTRACTION = "extraction"
    CLASSIFICATION = "classification"
    GENERAL = "general"


class ModelMetadata(BaseModel):
    id: str
    name: str
    provider: str
    type: ModelType
    tier: ModelTier
    input_cost_per_1m_tokens: float = Field(ge=0)
    output_cost_per_1m_tokens: float = Field(ge=0)
    context_window: int = Field(gt=0)
    capabilities: list[str] = Field(default_factory=list)
    enabled: bool = True
    avg_latency_ms: float = Field(default=500.0, ge=0)
    quality_score: float = Field(default=0.85, ge=0, le=1)


class ModelCreateRequest(BaseModel):
    id: str
    name: str
    provider: str
    type: ModelType = ModelType.API
    tier: ModelTier
    input_cost_per_1m_tokens: float = Field(ge=0)
    output_cost_per_1m_tokens: float = Field(ge=0)
    context_window: int = Field(gt=0)
    capabilities: list[str] = Field(default_factory=list)
    enabled: bool = True
    avg_latency_ms: float = Field(default=500.0, ge=0)
    quality_score: float = Field(default=0.85, ge=0, le=1)


class ModelUpdateRequest(BaseModel):
    name: str | None = None
    provider: str | None = None
    type: ModelType | None = None
    tier: ModelTier | None = None
    input_cost_per_1m_tokens: float | None = Field(default=None, ge=0)
    output_cost_per_1m_tokens: float | None = Field(default=None, ge=0)
    context_window: int | None = Field(default=None, gt=0)
    capabilities: list[str] | None = None
    enabled: bool | None = None
    avg_latency_ms: float | None = Field(default=None, ge=0)
    quality_score: float | None = Field(default=None, ge=0, le=1)


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded", "error"]
    app_name: str
    version: str
    environment: str


class RouterStatusResponse(BaseModel):
    router_type: str
    quality_floor: float
    cost_priority: float
    latency_priority: float
    fallback_enabled: bool
    max_fallback_attempts: int
    fallback_on_quality_below: float | None
    fallback_escalation: str
    enabled_models: int
    total_models: int
