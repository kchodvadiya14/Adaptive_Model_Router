"""Converters between internal chat schemas and OpenAI-compatible formats."""

from __future__ import annotations

import time
import uuid

from app.schemas.chat import ChatMessage, ChatRequest, ChatResponse
from app.schemas.openai import (
    OpenAIChatCompletionChoice,
    OpenAIChatCompletionRequest,
    OpenAIChatCompletionResponse,
    OpenAIMessage,
    OpenAIModel,
    OpenAIModelList,
    OpenAIRouterMetadata,
    OpenAIUsage,
)
from app.schemas.models import ModelMetadata

SUPPORTED_MESSAGE_ROLES = {"system", "user", "assistant"}
AUTO_MODEL = "auto"


def normalize_model_name(model: str) -> str:
    return model.strip().lower()


def resolve_model_name(model: str) -> str:
    if normalize_model_name(model) == AUTO_MODEL:
        return AUTO_MODEL
    return model.strip()


def to_chat_request(
    request: OpenAIChatCompletionRequest,
    *,
    quality_floor: float | None = None,
) -> ChatRequest:
    messages: list[ChatMessage] = []
    for message in request.messages:
        if message.role not in SUPPORTED_MESSAGE_ROLES:
            continue
        if not message.content or not message.content.strip():
            continue
        messages.append(ChatMessage(role=message.role, content=message.content.strip()))

    if not messages:
        raise ValueError("At least one supported message with non-empty content is required.")

    return ChatRequest(
        model=resolve_model_name(request.model),
        messages=messages,
        max_tokens=request.max_tokens or 1024,
        temperature=request.temperature if request.temperature is not None else 0.7,
        quality_floor=quality_floor,
    )


def to_openai_response(chat: ChatResponse) -> OpenAIChatCompletionResponse:
    router_metadata: OpenAIRouterMetadata | None = None
    if chat.routing or chat.routed or chat.fallback:
        router_metadata = OpenAIRouterMetadata(
            routed=chat.routed,
            selected_model=chat.model,
            model_tier=chat.tier,
            task_type=chat.routing.task_type if chat.routing else None,
            estimated_quality=chat.routing.estimated_quality if chat.routing else None,
            estimated_cost=chat.routing.estimated_cost if chat.routing else chat.cost.total_cost,
            cost_saved_vs_strong=chat.routing.cost_saved_vs_strong if chat.routing else None,
            fallback_used=bool(chat.fallback and chat.fallback.used),
            actual_cost=chat.cost.total_cost,
            latency_ms=chat.latency_ms,
        )

    return OpenAIChatCompletionResponse(
        id=f"chatcmpl-{uuid.uuid4().hex[:24]}",
        created=int(time.time()),
        model=chat.model,
        choices=[
            OpenAIChatCompletionChoice(
                index=0,
                message=OpenAIMessage(role="assistant", content=chat.content),
                finish_reason="stop",
            )
        ],
        usage=OpenAIUsage(
            prompt_tokens=chat.usage.input_tokens,
            completion_tokens=chat.usage.output_tokens,
            total_tokens=chat.usage.total_tokens,
        ),
        router=router_metadata,
    )


def to_openai_model_list(models: list[ModelMetadata], *, include_auto: bool = True) -> OpenAIModelList:
    created = int(time.time())
    data: list[OpenAIModel] = []

    if include_auto:
        data.append(
            OpenAIModel(
                id=AUTO_MODEL,
                created=created,
                owned_by="adaptive-router",
            )
        )

    for model in models:
        data.append(
            OpenAIModel(
                id=model.id,
                created=created,
                owned_by=model.provider,
            )
        )

    return OpenAIModelList(data=data)


def to_openai_model(model: ModelMetadata) -> OpenAIModel:
    return OpenAIModel(
        id=model.id,
        created=int(time.time()),
        owned_by=model.provider,
    )
