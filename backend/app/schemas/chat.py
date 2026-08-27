"""Pydantic schemas for chat API."""

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.routing import RoutingDecision


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1, max_length=32000)


class ChatRequest(BaseModel):
    model: str = Field(default="auto", description="Model ID from registry, or 'auto' for adaptive routing")
    messages: list[ChatMessage] = Field(min_length=1, max_length=50)
    max_tokens: int = Field(default=1024, ge=1, le=8192)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    quality_floor: float | None = Field(default=None, ge=0.0, le=1.0)


class TokenUsage(BaseModel):
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)


class CostBreakdown(BaseModel):
    input_cost: float = Field(ge=0)
    output_cost: float = Field(ge=0)
    total_cost: float = Field(ge=0)


class FallbackAttemptRecord(BaseModel):
    model_id: str
    model_tier: str
    success: bool
    reason: str | None = None
    latency_ms: float | None = None


class FallbackInfo(BaseModel):
    used: bool = False
    original_model: str
    final_model: str
    attempts: list[FallbackAttemptRecord] = Field(default_factory=list)
    escalation_reason: str | None = None


class ChatResponse(BaseModel):
    content: str
    model: str
    model_name: str
    provider: str
    tier: str
    usage: TokenUsage
    cost: CostBreakdown
    latency_ms: float = Field(ge=0)
    routed: bool = False
    routing: RoutingDecision | None = None
    fallback: FallbackInfo | None = None
