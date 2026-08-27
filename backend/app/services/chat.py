"""Chat orchestration service."""

from __future__ import annotations

import logging

from app.config.settings import get_settings
from app.db.repository import log_routing_event
from app.evaluation.judge import get_judge
from app.models.registry import get_model_registry
from app.providers.base import GenerationRequest, ProviderError, ProviderErrorCode
from app.providers.factory import get_provider_for_model
from app.router.base import get_router
from app.router.policy import estimate_prompt_cost
from app.schemas.chat import ChatRequest, ChatResponse, TokenUsage
from app.schemas.models import ModelMetadata, ModelTier
from app.schemas.routing import RouteRequest, RoutingDecision
from app.services.fallback import FallbackExecutor, build_fallback_info

logger = logging.getLogger(__name__)
AUTO_MODEL = "auto"


class ChatService:
    """Handles direct and routed LLM calls through provider adapters."""

    def _extract_user_prompt(self, request: ChatRequest) -> str:
        user_messages = [message.content for message in request.messages if message.role == "user"]
        if not user_messages:
            raise ProviderError(
                "At least one user message is required for routing.",
                code=ProviderErrorCode.PROVIDER_ERROR,
            )
        return user_messages[-1]

    def _route_prompt(self, prompt: str, quality_floor: float | None = None) -> RoutingDecision:
        router = get_router()
        configuration = {"quality_floor": quality_floor} if quality_floor is not None else None
        return router.route(RouteRequest(prompt=prompt), configuration=configuration)

    async def _evaluate_response_quality(self, prompt: str, response: str) -> float | None:
        settings = get_settings()
        if not settings.evaluate_on_chat:
            return None
        if settings.judge_provider == "openai" and not settings.openai_api_key:
            return None
        judge = get_judge()
        score = await judge.evaluate(prompt, response)
        return score.overall

    async def chat(self, request: ChatRequest) -> ChatResponse:
        settings = get_settings()
        registry = get_model_registry()
        routing: RoutingDecision | None = None
        original_model_id = request.model
        model_id = request.model
        prompt = self._extract_user_prompt(request)

        if model_id == AUTO_MODEL:
            routing = self._route_prompt(prompt, quality_floor=request.quality_floor)
            model_id = routing.selected_model
            original_model_id = model_id
            logger.info(
                "Routed prompt task=%s difficulty=%.2f -> model=%s tier=%s",
                routing.task_type,
                routing.difficulty,
                routing.selected_model,
                routing.model_tier,
            )
        else:
            model = registry.get_model(model_id)
            if not model:
                raise ProviderError(
                    f"Model '{model_id}' not found in registry.",
                    code=ProviderErrorCode.MODEL_UNAVAILABLE,
                )
            if not model.enabled:
                raise ProviderError(
                    f"Model '{model_id}' is disabled.",
                    code=ProviderErrorCode.MODEL_UNAVAILABLE,
                )

        messages = [message.model_dump() for message in request.messages]
        generation_request = GenerationRequest(
            messages=messages,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
        )

        fallback_executor = FallbackExecutor(settings=settings, registry=registry)

        quality_evaluator = None
        if request.model == AUTO_MODEL:

            async def quality_evaluator(model: ModelMetadata, generation) -> float | None:
                return await self._evaluate_response_quality(prompt, generation.content)

        logger.info("Generating response with model=%s (fallback=%s)", model_id, settings.fallback_enabled)
        model, generation, attempt_records = await fallback_executor.generate_with_fallback(
            model_id,
            generation_request,
            quality_evaluator=quality_evaluator,
        )
        fallback_info = build_fallback_info(original_model_id, model.id, attempt_records)

        provider = get_provider_for_model(model)
        cost = provider.estimate_cost(generation.input_tokens, generation.output_tokens)
        actual_quality = await self._evaluate_response_quality(prompt, generation.content)

        strong_model = registry.get_primary_model_for_tier(ModelTier.STRONG)
        strong_baseline_cost = (
            routing.strong_model_baseline_cost
            if routing
            else estimate_prompt_cost(strong_model, prompt, expected_output_tokens=generation.output_tokens)
            if strong_model
            else cost.total_cost
        )

        try:
            log_routing_event(
                prompt=prompt,
                task_type=routing.task_type if routing else None,
                difficulty=routing.difficulty if routing else None,
                router_type=settings.router_type,
                selected_model=model.id,
                model_tier=model.tier.value,
                estimated_cost=routing.estimated_cost if routing else cost.total_cost,
                actual_cost=cost.total_cost,
                estimated_quality=routing.estimated_quality if routing else None,
                actual_quality=actual_quality,
                latency_ms=generation.latency_ms,
                routed=request.model == AUTO_MODEL,
                strong_baseline_cost=strong_baseline_cost,
                input_tokens=generation.input_tokens,
                output_tokens=generation.output_tokens,
                store_prompt=settings.store_prompts,
                fallback_used=fallback_info.used if fallback_info else False,
                fallback_attempts=len(attempt_records),
                original_model=original_model_id,
                fallback_reason=fallback_info.escalation_reason if fallback_info else None,
            )
        except Exception as exc:
            logger.warning("Failed to log routing event: %s", exc)

        return ChatResponse(
            content=generation.content,
            model=model.id,
            model_name=model.name,
            provider=model.provider,
            tier=model.tier.value,
            usage=TokenUsage(
                input_tokens=generation.input_tokens,
                output_tokens=generation.output_tokens,
                total_tokens=generation.input_tokens + generation.output_tokens,
            ),
            cost=cost,
            latency_ms=round(generation.latency_ms, 2),
            routed=request.model == AUTO_MODEL,
            routing=routing,
            fallback=fallback_info,
        )


_chat_service: ChatService | None = None


def get_chat_service() -> ChatService:
    global _chat_service
    if _chat_service is None:
        _chat_service = ChatService()
    return _chat_service
