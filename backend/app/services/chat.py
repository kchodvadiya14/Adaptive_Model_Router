"""Chat orchestration service."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from app.config.settings import get_settings
from app.db.repository import log_routing_event
from app.evaluation.judge import get_judge
from app.models.registry import get_model_registry
from app.providers.base import GenerationRequest, ProviderError, ProviderErrorCode
from app.providers.factory import get_provider_for_model
from app.router.base import get_router
from app.router.capabilities import CapabilityExclusion, CapabilityRequirements, NoCapableModelError
from app.router.constraints import RoutingConstraints, model_meets_constraints
from app.router.policy import PreferredModelUnavailableError, estimate_prompt_cost
from app.schemas.chat import ChatRequest, ChatResponse, TokenUsage
from app.schemas.models import ModelMetadata, ModelTier
from app.schemas.routing import RouteRequest, RoutingDecision
from app.services.deadline import STAGE_EVALUATION, RequestDeadline, run_within
from app.services.fallback import FallbackExecutor, build_fallback_info
from app.services.outcomes import OutcomeContext, OutcomeRecorder
from app.utils.tokens import estimate_messages_tokens

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

    def _detect_capability_requirements(self, request: ChatRequest) -> CapabilityRequirements:
        """Derive hard routing requirements from the request as sent — no separate
        multimodal/tool-call parsing system, just the fields already on ChatRequest."""
        requires_vision = any(message.has_image for message in request.messages)
        requires_tools = bool(request.tools)
        input_tokens = estimate_messages_tokens(
            [{"content": message.content} for message in request.messages]
        )
        min_context_tokens = input_tokens + request.max_tokens
        return CapabilityRequirements(
            requires_vision=requires_vision,
            requires_tools=requires_tools,
            min_context_tokens=min_context_tokens,
        )

    def _route_prompt(
        self,
        prompt: str,
        quality_floor: float | None = None,
        requirements: CapabilityRequirements | None = None,
        constraints: RoutingConstraints | None = None,
        preferred_model: str | None = None,
    ) -> RoutingDecision:
        router = get_router()
        configuration: dict[str, Any] = {}
        if quality_floor is not None:
            configuration["quality_floor"] = quality_floor
        if requirements is not None:
            configuration["required_capabilities"] = {
                "requires_vision": requirements.requires_vision,
                "requires_tools": requirements.requires_tools,
                "min_context_tokens": requirements.min_context_tokens,
            }
        if constraints is not None and constraints.is_active():
            if constraints.max_cost is not None:
                configuration["max_cost"] = constraints.max_cost
            if constraints.max_latency_ms is not None:
                configuration["max_latency_ms"] = constraints.max_latency_ms
        if preferred_model:
            configuration["preferred_model"] = preferred_model
        return router.route(RouteRequest(prompt=prompt), configuration=configuration or None)

    @staticmethod
    def _check_pinned_model_constraints(
        model: ModelMetadata,
        prompt: str,
        constraints: RoutingConstraints,
    ) -> None:
        """A pinned model is the caller's explicit choice, but max_cost / max_latency_ms
        are explicit too — a pin that breaks them is rejected rather than silently run."""
        eligible, reason = model_meets_constraints(model, estimate_prompt_cost(model, prompt), constraints)
        if not eligible:
            raise NoCapableModelError(
                CapabilityRequirements(),
                [
                    CapabilityExclusion(
                        tier=model.tier.value,
                        model_id=model.id,
                        model_name=model.name,
                        reason=reason or "does not meet the request's constraints",
                    )
                ],
                constraints,
            )

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
        request_id = request.request_id or uuid.uuid4().hex
        deadline = (
            RequestDeadline.start(
                request.timeout_ms,
                min_attempt_budget_ms=settings.request_min_attempt_budget_ms,
                request_id=request_id,
            )
            if request.timeout_ms is not None
            else None
        )
        original_model_id = request.model
        model_id = request.model
        prompt = self._extract_user_prompt(request)
        constraints = RoutingConstraints(max_cost=request.max_cost, max_latency_ms=request.max_latency_ms)

        if model_id == AUTO_MODEL:
            requirements = self._detect_capability_requirements(request)
            try:
                routing = self._route_prompt(
                    prompt,
                    quality_floor=request.quality_floor,
                    requirements=requirements,
                    constraints=constraints,
                    preferred_model=request.preferred_model,
                )
            except PreferredModelUnavailableError as exc:
                raise ProviderError(str(exc), code=ProviderErrorCode.MODEL_UNAVAILABLE) from exc
            model_id = routing.selected_model
            original_model_id = model_id
            logger.info(
                "[request_id=%s] Routed prompt task=%s difficulty=%.2f -> model=%s tier=%s preferred=%s honored=%s",
                request_id,
                routing.task_type,
                routing.difficulty,
                routing.selected_model,
                routing.model_tier,
                routing.preferred_model,
                routing.preferred_model_honored,
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
            if constraints.is_active():
                self._check_pinned_model_constraints(model, prompt, constraints)

        # Only role/content go to the provider; has_image is routing metadata, not
        # something GenerationRequest's dict[str, str] messages can carry.
        messages = [{"role": message.role, "content": message.content} for message in request.messages]
        generation_request = GenerationRequest(
            messages=messages,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
        )

        fallback_executor = FallbackExecutor(settings=settings, registry=registry)

        # Quality-based escalation applies to both "auto" and a pinned model: whichever model
        # generated the response, a low score should still trigger a tier escalation. The
        # executor itself gates this on FALLBACK_ENABLED / FALLBACK_ON_QUALITY_BELOW, and stops
        # at the strongest tier, so passing the evaluator unconditionally is safe here.
        async def quality_evaluator(model: ModelMetadata, generation) -> float | None:
            return await self._evaluate_response_quality(prompt, generation.content)

        candidate_filter = None
        if constraints.is_active():

            def candidate_filter(candidate: ModelMetadata) -> bool:
                eligible, _reason = model_meets_constraints(
                    candidate, estimate_prompt_cost(candidate, prompt), constraints
                )
                return eligible

        logger.info(
            "[request_id=%s] Generating response with model=%s (fallback=%s)",
            request_id,
            model_id,
            settings.fallback_enabled,
        )
        fallback_result = await fallback_executor.execute_with_fallback(
            model_id,
            generation_request,
            quality_evaluator=quality_evaluator,
            candidate_filter=candidate_filter,
            deadline=deadline,
            outcome_context=OutcomeContext(
                request_id=request_id,
                task_type=routing.task_type if routing else None,
                difficulty=routing.difficulty if routing else None,
            ),
        )
        model = fallback_result.model
        generation = fallback_result.generation
        attempt_records = fallback_result.attempts
        fallback_info = build_fallback_info(original_model_id, model.id, attempt_records)

        provider = get_provider_for_model(model)
        cost = provider.estimate_cost(generation.input_tokens, generation.output_tokens)
        # Reuse the score the fallback executor already computed for this exact response.
        if fallback_result.quality_evaluated:
            actual_quality = fallback_result.quality
        else:
            actual_quality = await run_within(
                deadline,
                self._evaluate_response_quality(prompt, generation.content),
                STAGE_EVALUATION,
                model.id,
            )
            # No escalation threshold applies on this path, so this is a score only.
            OutcomeRecorder().attach_quality(
                fallback_result.final_outcome_id, actual_quality, quality_failure=False
            )

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
                request_id=request_id,
                user_id=request.user_id,
                session_id=request.session_id,
                tags=request.tags,
                preferred_model=request.preferred_model,
            )
        except Exception as exc:
            logger.warning("[request_id=%s] Failed to log routing event: %s", request_id, exc)

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
            request_id=request_id,
        )


_chat_service: ChatService | None = None


def get_chat_service() -> ChatService:
    global _chat_service
    if _chat_service is None:
        _chat_service = ChatService()
    return _chat_service
