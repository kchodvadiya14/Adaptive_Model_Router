"""OpenAI-compatible API schemas."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class OpenAIErrorDetail(BaseModel):
    message: str
    type: str = "invalid_request_error"
    param: str | None = None
    code: str | None = None


class OpenAIErrorResponse(BaseModel):
    error: OpenAIErrorDetail


class OpenAIMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool", "function"]
    content: str | None = None


class OpenAIChatCompletionRequest(BaseModel):
    model: str
    messages: list[OpenAIMessage] = Field(min_length=1)
    max_tokens: int | None = Field(default=None, ge=1, le=8192)
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    stream: bool = False
    tools: list[dict[str, Any]] | None = Field(
        default=None,
        description="OpenAI-style tool/function definitions, used for capability-aware routing.",
    )
    user: str | None = Field(default=None, description="OpenAI end-user identifier; recorded as user_id.")
    metadata: dict[str, str] | None = Field(
        default=None,
        description="OpenAI request metadata key/value pairs; recorded as usage tags.",
    )

    model_config = {"extra": "ignore"}


class OpenAIChatCompletionChoice(BaseModel):
    index: int
    message: OpenAIMessage
    finish_reason: Literal["stop", "length", "content_filter", "tool_calls"] | None = "stop"


class OpenAIUsage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class OpenAIRouterMetadata(BaseModel):
    routed: bool
    selected_model: str
    model_tier: str
    task_type: str | None = None
    estimated_quality: float | None = None
    estimated_cost: float | None = None
    cost_saved_vs_strong: float | None = None
    fallback_used: bool = False
    actual_cost: float | None = None
    latency_ms: float | None = None
    request_id: str | None = None


class OpenAIChatCompletionResponse(BaseModel):
    id: str
    object: Literal["chat.completion"] = "chat.completion"
    created: int
    model: str
    choices: list[OpenAIChatCompletionChoice]
    usage: OpenAIUsage
    router: OpenAIRouterMetadata | None = None


class OpenAIModel(BaseModel):
    id: str
    object: Literal["model"] = "model"
    created: int
    owned_by: str


class OpenAIModelList(BaseModel):
    object: Literal["list"] = "list"
    data: list[OpenAIModel]
