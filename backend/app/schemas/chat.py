"""Pydantic schemas for chat API."""

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.routing import RoutingDecision

MAX_TAGS = 20


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1, max_length=32000)
    has_image: bool = Field(
        default=False,
        description="True if this message includes image/vision input; used for capability-aware routing.",
    )


class ChatRequest(BaseModel):
    model: str = Field(default="auto", description="Model ID from registry, or 'auto' for adaptive routing")
    messages: list[ChatMessage] = Field(min_length=1, max_length=50)
    max_tokens: int = Field(default=1024, ge=1, le=8192)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    quality_floor: float | None = Field(default=None, ge=0.0, le=1.0)
    tools: list[dict[str, Any]] | None = Field(
        default=None,
        description="OpenAI-style tool/function definitions. A non-empty list means the "
        "request requires tool/function-calling support for capability-aware routing.",
    )

    # Request metadata — all optional, recorded in the routing log for usage reporting.
    request_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=128,
        description="Caller-supplied correlation ID. Generated automatically when omitted.",
    )
    user_id: str | None = Field(default=None, min_length=1, max_length=128)
    session_id: str | None = Field(default=None, min_length=1, max_length=128)
    tags: dict[str, str] | None = Field(
        default=None,
        max_length=MAX_TAGS,
        description="Free-form key/value labels (e.g. app, feature, environment) for usage breakdowns.",
    )

    # Routing preferences and constraints — only affect model selection, never bypass
    # capability, health, or constraint checks.
    preferred_model: str | None = Field(
        default=None,
        min_length=1,
        description="With model='auto': use this model if it passes every eligibility check, "
        "otherwise route normally and report why it was not used.",
    )
    max_cost: float | None = Field(default=None, ge=0, description="Maximum estimated cost per request (USD).")
    max_latency_ms: float | None = Field(default=None, ge=0, description="Maximum average model latency (ms).")

    # Execution deadline — distinct from max_latency_ms, which only filters routing
    # candidates by their average-latency metadata.
    timeout_ms: int | None = Field(
        default=None,
        gt=0,
        le=600_000,
        description="Overall wall-clock budget for the whole request (generation, fallback, "
        "evaluation, escalation). Omit for no request-level deadline.",
    )

    @model_validator(mode="after")
    def _preferred_model_matches_pin(self) -> "ChatRequest":
        if self.preferred_model and self.model != "auto" and self.preferred_model != self.model:
            raise ValueError(
                f"preferred_model '{self.preferred_model}' conflicts with model '{self.model}'; "
                "use model='auto' with preferred_model, or pin the model directly."
            )
        return self


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
    request_id: str | None = None
