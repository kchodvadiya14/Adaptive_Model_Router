"""Fallback chain and quality escalation for chat requests."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from app.config.settings import Settings, get_settings
from app.models.registry import ModelRegistry, get_model_registry
from app.providers.base import GenerationRequest, GenerationResponse, ProviderError, ProviderErrorCode
from app.providers.factory import get_provider_for_model
from app.router import health
from app.schemas.chat import FallbackAttemptRecord, FallbackInfo
from app.schemas.models import ModelMetadata, ModelTier
from app.services.deadline import (
    STAGE_ESCALATION,
    STAGE_EVALUATION,
    STAGE_FALLBACK,
    STAGE_GENERATION,
    RequestDeadline,
    RequestTimeoutError,
    run_within,
)
from app.db.outcome_repository import (
    OUTCOME_NON_RETRYABLE_FAILURE,
    OUTCOME_RETRYABLE_FAILURE,
    OUTCOME_SUCCESS,
    OUTCOME_TIMEOUT,
)
from app.services.outcomes import OutcomeContext, OutcomeRecorder

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


def _is_healthy(model_id: str) -> bool:
    """Read-only check — never claims a half-open trial slot. See app/router/health.py."""
    available, _reason = health.is_routable(model_id)
    return available


CandidateFilter = Callable[[ModelMetadata], bool]


def build_fallback_chain(
    initial_model_id: str,
    registry: ModelRegistry,
    *,
    escalation: str = "tier_up",
    max_attempts: int = 3,
    candidate_filter: CandidateFilter | None = None,
) -> list[str]:
    """Build ordered list of model IDs to attempt.

    Models whose circuit is currently open are skipped — "before attempting a model,
    check whether its circuit is available." If skipping health-ineligible candidates
    would leave nothing to try at all, the original unfiltered chain is used instead
    (fail open rather than refuse to even attempt anything), since something must
    still be tried.

    `candidate_filter` (e.g. a request's max_cost / max_latency_ms) applies to the
    escalation candidates only; the initial model was already chosen or pinned. Unlike
    health, it is never relaxed: a model that breaks a caller's constraint is not tried.
    """
    initial = registry.get_model(initial_model_id)
    if not initial:
        return [initial_model_id]

    chain = [initial_model_id]

    def allowed(candidate: ModelMetadata) -> bool:
        return candidate_filter is None or candidate_filter(candidate)

    if escalation == "strong_only":
        strong = registry.get_primary_model_for_tier(ModelTier.STRONG)
        if strong and strong.id not in chain and allowed(strong):
            chain.append(strong.id)
    else:
        start_idx = TIER_ORDER.index(initial.tier)
        for tier in TIER_ORDER[start_idx + 1 :]:
            candidate = registry.get_primary_model_for_tier(tier)
            if candidate and candidate.id not in chain and allowed(candidate):
                chain.append(candidate.id)

    chain = chain[: max(1, max_attempts)]

    healthy_chain = [model_id for model_id in chain if _is_healthy(model_id)]
    return healthy_chain or chain


def get_quality_escalation_model(
    current_model: ModelMetadata,
    registry: ModelRegistry,
    *,
    escalation: str = "tier_up",
    candidate_filter: CandidateFilter | None = None,
) -> ModelMetadata | None:
    """Next tier's model for quality-triggered escalation, skipping any candidate
    whose circuit is currently open or that fails `candidate_filter`, in favor of the
    next eligible tier up."""

    def usable(candidate: ModelMetadata) -> bool:
        return _is_healthy(candidate.id) and (candidate_filter is None or candidate_filter(candidate))

    if escalation == "strong_only":
        strong = registry.get_primary_model_for_tier(ModelTier.STRONG)
        if strong and strong.id != current_model.id and usable(strong):
            return strong
        return None

    start_idx = TIER_ORDER.index(current_model.tier)
    for tier in TIER_ORDER[start_idx + 1 :]:
        candidate = registry.get_primary_model_for_tier(tier)
        if candidate and candidate.id != current_model.id and usable(candidate):
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


@dataclass
class FallbackResult:
    """Outcome of a fallback run, including the judge score of the returned response.

    ``quality_evaluated`` is True when the quality evaluator already scored ``generation``,
    so callers can reuse ``quality`` instead of judging the same response again.
    """

    model: ModelMetadata
    generation: GenerationResponse
    attempts: list[FallbackAttemptRecord] = field(default_factory=list)
    quality: float | None = None
    quality_evaluated: bool = False
    # Outcome row for the attempt whose response is returned, so a caller that judges it
    # later can attach the score.
    final_outcome_id: int | None = None


class FallbackExecutor:
    """Executes generation with provider-error fallback and optional quality escalation."""

    def __init__(self, settings: Settings | None = None, registry: ModelRegistry | None = None) -> None:
        self.settings = settings or get_settings()
        self.registry = registry or get_model_registry()

    def _validate_model(self, model_id: str) -> tuple[ModelMetadata, bool]:
        """Returns the model and whether this call claimed its half-open health trial."""
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
        # Mutating check, right before we actually attempt generation: this is where an
        # OPEN circuit past its cooldown gets atomically claimed as the one half-open
        # trial. None of these three checks (not found / disabled / no API key) are
        # generation attempts, so none of them ever touch health recording.
        available, reason, claimed_trial = health.acquire_for_generation(model.id, model.provider)
        if not available:
            raise ProviderError(
                f"Model '{model.id}' is temporarily unavailable: {reason}",
                code=ProviderErrorCode.MODEL_UNAVAILABLE,
            )
        return model, claimed_trial

    async def _try_generate(
        self,
        model_id: str,
        request: GenerationRequest,
        *,
        deadline: RequestDeadline | None = None,
        stage: str = STAGE_GENERATION,
        recorder: OutcomeRecorder | None = None,
    ) -> tuple[ModelMetadata, GenerationResponse]:
        recorder = recorder or OutcomeRecorder()
        # Checked before claiming a half-open trial, so an exhausted budget never
        # consumes one.
        if deadline is not None:
            deadline.ensure_budget(stage, model_id)
        model, claimed_trial = self._validate_model(model_id)
        provider = get_provider_for_model(model)
        started = time.perf_counter()

        def elapsed_ms() -> float:
            return (time.perf_counter() - started) * 1000.0

        try:
            generation = await run_within(deadline, provider.generate(request), stage, model.id)
        except RequestTimeoutError as exc:
            # The request ran out of time; that says nothing about the model. No health
            # failure is recorded, and a half-open trial is given back so the circuit
            # isn't left waiting on a verdict that will never arrive. The attempt is
            # still recorded as feedback, as a timeout rather than a provider failure.
            if claimed_trial:
                health.release_trial(model.id)
            if exc.started:
                recorder.record_attempt(
                    model,
                    stage=stage,
                    outcome=OUTCOME_TIMEOUT,
                    success=False,
                    latency_ms=elapsed_ms(),
                    error_code="request_timeout",
                )
            raise
        except ProviderError as exc:
            # Only an actual generation failure that we'd retry elsewhere for counts as
            # a health signal. Non-retryable errors (bad request, auth/config issues,
            # etc.) are the caller's problem, not the model being unhealthy — reuses
            # the existing retryable-error classification exactly, nothing new here.
            retryable = is_retryable_error(exc.code)
            if retryable:
                health.record_failure(model.id, model.provider, str(exc))
            recorder.record_attempt(
                model,
                stage=stage,
                outcome=OUTCOME_RETRYABLE_FAILURE if retryable else OUTCOME_NON_RETRYABLE_FAILURE,
                success=False,
                latency_ms=elapsed_ms(),
                error_code=exc.code.value,
            )
            raise
        except Exception as exc:
            # Adapter bug or other unexpected error: not classified for health (unchanged),
            # but still a failed attempt worth knowing about.
            recorder.record_attempt(
                model,
                stage=stage,
                outcome=OUTCOME_NON_RETRYABLE_FAILURE,
                success=False,
                latency_ms=elapsed_ms(),
                error_code=f"unexpected_error:{type(exc).__name__}",
            )
            raise
        else:
            health.record_success(model.id, model.provider)
            recorder.record_attempt(
                model,
                stage=stage,
                outcome=OUTCOME_SUCCESS,
                success=True,
                latency_ms=generation.latency_ms,
                estimated_cost=provider.estimate_cost(generation.input_tokens, generation.output_tokens).total_cost,
            )
            return model, generation

    async def generate_with_fallback(
        self,
        initial_model_id: str,
        request: GenerationRequest,
        *,
        quality_evaluator: QualityEvaluator | None = None,
    ) -> tuple[ModelMetadata, GenerationResponse, list[FallbackAttemptRecord]]:
        result = await self.execute_with_fallback(
            initial_model_id,
            request,
            quality_evaluator=quality_evaluator,
        )
        return result.model, result.generation, result.attempts

    async def execute_with_fallback(
        self,
        initial_model_id: str,
        request: GenerationRequest,
        *,
        quality_evaluator: QualityEvaluator | None = None,
        candidate_filter: CandidateFilter | None = None,
        deadline: RequestDeadline | None = None,
        outcome_context: OutcomeContext | None = None,
    ) -> FallbackResult:
        """`deadline`, when given, is the request's single overall budget: every
        generation attempt, fallback attempt, evaluation and escalation below runs inside
        whatever remains of it, and a step with too little budget left is not started.

        Every attempt that reaches a provider is recorded as a model outcome (see
        app/services/outcomes.py); `outcome_context` supplies request_id / task / difficulty."""
        settings = self.settings
        attempt_records: list[FallbackAttemptRecord] = []
        recorder = OutcomeRecorder(outcome_context)

        if settings.fallback_enabled:
            chain = build_fallback_chain(
                initial_model_id,
                self.registry,
                escalation=settings.fallback_escalation,
                max_attempts=settings.max_fallback_attempts,
                candidate_filter=candidate_filter,
            )
        else:
            chain = [initial_model_id]

        model: ModelMetadata | None = None
        generation: GenerationResponse | None = None
        last_error: ProviderError | None = None

        for attempt_index, model_id in enumerate(chain):
            stage = STAGE_GENERATION if attempt_index == 0 else STAGE_FALLBACK
            try:
                model, generation = await self._try_generate(
                    model_id, request, deadline=deadline, stage=stage, recorder=recorder
                )
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

        result = FallbackResult(
            model=model,
            generation=generation,
            attempts=attempt_records,
            final_outcome_id=recorder.last_outcome_id,
        )

        if (
            settings.fallback_enabled
            and settings.fallback_on_quality_below is not None
            and quality_evaluator is not None
        ):
            quality = await run_within(
                deadline, quality_evaluator(model, generation), STAGE_EVALUATION, model.id
            )
            result.quality = quality
            result.quality_evaluated = True
            quality_failed = quality is not None and quality < settings.fallback_on_quality_below
            recorder.attach_quality(result.final_outcome_id, quality, quality_failure=quality_failed)
            if quality_failed:
                next_model = get_quality_escalation_model(
                    model,
                    self.registry,
                    escalation=settings.fallback_escalation,
                    candidate_filter=candidate_filter,
                )
                if next_model:
                    try:
                        esc_model, esc_generation = await self._try_generate(
                            next_model.id,
                            request,
                            deadline=deadline,
                            stage=STAGE_ESCALATION,
                            recorder=recorder,
                        )
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
                    else:
                        attempt_records.append(
                            FallbackAttemptRecord(
                                model_id=esc_model.id,
                                model_tier=esc_model.tier.value,
                                success=True,
                                reason="quality_escalation",
                                latency_ms=esc_generation.latency_ms,
                            )
                        )
                        result.model = esc_model
                        result.generation = esc_generation
                        result.final_outcome_id = recorder.last_outcome_id
                        # Score the response actually returned; the first score belonged to the
                        # response that was just replaced. Judge errors propagate, as before.
                        result.quality = await run_within(
                            deadline,
                            quality_evaluator(esc_model, esc_generation),
                            STAGE_EVALUATION,
                            esc_model.id,
                        )
                        recorder.attach_quality(
                            result.final_outcome_id,
                            result.quality,
                            quality_failure=result.quality is not None
                            and result.quality < settings.fallback_on_quality_below,
                        )

        return result
