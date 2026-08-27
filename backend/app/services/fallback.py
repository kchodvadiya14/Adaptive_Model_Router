"""Fallback chain and quality escalation for chat requests."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from app.config.settings import Settings, get_settings
from app.models.registry import ModelRegistry, get_model_registry
from app.providers.base import GenerationRequest, GenerationResponse, ProviderError, ProviderErrorCode
from app.providers.factory import get_provider_for_model
from app.schemas.chat import FallbackAttemptRecord, FallbackInfo
from app.schemas.models import ModelMetadata, ModelTier

TIER_ORDER = (ModelTier.SMALL, ModelTier.MEDIUM, ModelTier.STRONG)

RETRYABLE_ERROR_CODES = {
    ProviderErrorCode.TIMEOUT,
    ProviderErrorCode.RATE_LIMIT,
    ProviderErrorCode.NETWORK_ERROR,
    ProviderErrorCode.INVALID_RESPONSE,
    ProviderErrorCode.PROVIDER_ERROR,
}


def is_retryable_error(code: ProviderErrorCode) -> bool:
    return code in RETRYABLE_ERROR_CODES


def build_fallback_chain(
    initial_model_id: str,
    registry: ModelRegistry,
    *,
    escalation: str = "tier_up",
    max_attempts: int = 3,
) -> list[str]:
    """Build ordered list of model IDs to attempt."""
    initial = registry.get_model(initial_model_id)
    if not initial:
        return [initial_model_id]

    chain = [initial_model_id]

    if escalation == "strong_only":
        strong = registry.get_primary_model_for_tier(ModelTier.STRONG)
        if strong and strong.id not in chain:
            chain.append(strong.id)
    else:
        start_idx = TIER_ORDER.index(initial.tier)
        for tier in TIER_ORDER[start_idx + 1 :]:
            candidate = registry.get_primary_model_for_tier(tier)
            if candidate and candidate.id not in chain:
                chain.append(candidate.id)

    return chain[: max(1, max_attempts)]


def get_quality_escalation_model(
    current_model: ModelMetadata,
    registry: ModelRegistry,
    *,
    escalation: str = "tier_up",
) -> ModelMetadata | None:
    if escalation == "strong_only":
        strong = registry.get_primary_model_for_tier(ModelTier.STRONG)
        if strong and strong.id != current_model.id:
            return strong
        return None

    start_idx = TIER_ORDER.index(current_model.tier)
    for tier in TIER_ORDER[start_idx + 1 :]:
        candidate = registry.get_primary_model_for_tier(tier)
        if candidate and candidate.id != current_model.id:
            return candidate
    return None


def build_fallback_info(
    original_model_id: str,
    final_model_id: str,
    attempt_records: list[FallbackAttemptRecord],
) -> FallbackInfo | None:
    used = (
        final_model_id != original_model_id
        or len(attempt_records) > 1
        or any(not record.success for record in attempt_records)
    )
    if not used:
        return None

    escalation_reason: str | None = None
    if any(record.reason == "quality_escalation" for record in attempt_records):
        escalation_reason = "quality_below_threshold"
    elif any(not record.success for record in attempt_records):
        escalation_reason = "provider_error"

    return FallbackInfo(
        used=True,
        original_model=original_model_id,
        final_model=final_model_id,
        attempts=attempt_records,
        escalation_reason=escalation_reason,
    )


QualityEvaluator = Callable[[ModelMetadata, GenerationResponse], Awaitable[float | None]]


class FallbackExecutor:
    """Executes generation with provider-error fallback and optional quality escalation."""

    def __init__(self, settings: Settings | None = None, registry: ModelRegistry | None = None) -> None:
        self.settings = settings or get_settings()
        self.registry = registry or get_model_registry()

    def _validate_model(self, model_id: str) -> ModelMetadata:
        model = self.registry.get_model(model_id)
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
        provider = get_provider_for_model(model)
        if not provider.is_available():
            raise ProviderError(
                f"Provider '{model.provider}' is not configured for model '{model.id}'.",
                code=ProviderErrorCode.MISSING_API_KEY,
            )
        return model

    async def _try_generate(
        self,
        model_id: str,
        request: GenerationRequest,
    ) -> tuple[ModelMetadata, GenerationResponse]:
        model = self._validate_model(model_id)
        provider = get_provider_for_model(model)
        generation = await provider.generate(request)
        return model, generation

    async def generate_with_fallback(
        self,
        initial_model_id: str,
        request: GenerationRequest,
        *,
        quality_evaluator: QualityEvaluator | None = None,
    ) -> tuple[ModelMetadata, GenerationResponse, list[FallbackAttemptRecord]]:
        settings = self.settings
        attempt_records: list[FallbackAttemptRecord] = []

        if settings.fallback_enabled:
            chain = build_fallback_chain(
                initial_model_id,
                self.registry,
                escalation=settings.fallback_escalation,
                max_attempts=settings.max_fallback_attempts,
            )
        else:
            chain = [initial_model_id]

        model: ModelMetadata | None = None
        generation: GenerationResponse | None = None
        last_error: ProviderError | None = None

        for model_id in chain:
            try:
                model, generation = await self._try_generate(model_id, request)
                attempt_records.append(
                    FallbackAttemptRecord(
                        model_id=model.id,
                        model_tier=model.tier.value,
                        success=True,
                        reason="success",
                        latency_ms=generation.latency_ms,
                    )
                )
                break
            except ProviderError as exc:
                failed_model = self.registry.get_model(model_id)
                attempt_records.append(
                    FallbackAttemptRecord(
                        model_id=model_id,
                        model_tier=failed_model.tier.value if failed_model else "unknown",
                        success=False,
                        reason=exc.code.value,
                        latency_ms=None,
                    )
                )
                last_error = exc
                if not settings.fallback_enabled or not is_retryable_error(exc.code):
                    raise
                continue

        if model is None or generation is None:
            assert last_error is not None
            raise last_error

        if (
            settings.fallback_enabled
            and settings.fallback_on_quality_below is not None
            and quality_evaluator is not None
        ):
            quality = await quality_evaluator(model, generation)
            if quality is not None and quality < settings.fallback_on_quality_below:
                next_model = get_quality_escalation_model(
                    model,
                    self.registry,
                    escalation=settings.fallback_escalation,
                )
                if next_model:
                    try:
                        esc_model, esc_generation = await self._try_generate(next_model.id, request)
                        attempt_records.append(
                            FallbackAttemptRecord(
                                model_id=esc_model.id,
                                model_tier=esc_model.tier.value,
                                success=True,
                                reason="quality_escalation",
                                latency_ms=esc_generation.latency_ms,
                            )
                        )
                        model = esc_model
                        generation = esc_generation
                    except ProviderError as exc:
                        attempt_records.append(
                            FallbackAttemptRecord(
                                model_id=next_model.id,
                                model_tier=next_model.tier.value,
                                success=False,
                                reason=f"quality_escalation_failed:{exc.code.value}",
                                latency_ms=None,
                            )
                        )

        return model, generation, attempt_records
