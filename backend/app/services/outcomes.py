"""Per-attempt outcome recording for historical routing performance.

Data collection only: nothing here feeds back into routing decisions.

Outcome definitions (one row per attempt that actually called a provider):

- `success`               the provider returned a response.
- `quality_failure`       the provider returned a response, but the judge scored it below
                          FALLBACK_ON_QUALITY_BELOW. `success` stays true: the model
                          answered, the answer just wasn't good enough.
- `retryable_failure`     provider error in the existing retryable classification
                          (timeout/rate limit/network/invalid response/provider error).
- `non_retryable_failure` any other provider error, or an unexpected exception.
- `timeout`               the request's own timeout_ms deadline cut the call off. Not a
                          provider failure; health is unaffected, as before.

`fallback_used` on an attempt means the gateway went on to another model after it
(provider-error fallback or quality escalation). `stage` records how the attempt itself
was reached: generation, fallback, or escalation.

Not recorded: models refused before any provider call (circuit open, disabled, missing
API key, or a deadline already exhausted) — there is no model behavior to measure.
Recording failures are logged and swallowed so feedback collection never breaks a request.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.db import outcome_repository
from app.schemas.models import ModelMetadata
from app.services.deadline import STAGE_GENERATION

logger = logging.getLogger(__name__)


@dataclass
class OutcomeContext:
    request_id: str | None = None
    task_type: str | None = None
    difficulty: float | None = None


class OutcomeRecorder:
    """Records the attempts of a single request and links consecutive attempts."""

    def __init__(self, context: OutcomeContext | None = None) -> None:
        self.context = context or OutcomeContext()
        self.last_outcome_id: int | None = None

    def record_attempt(
        self,
        model: ModelMetadata,
        *,
        stage: str,
        outcome: str,
        success: bool,
        latency_ms: float | None,
        estimated_cost: float | None = None,
        error_code: str | None = None,
    ) -> int | None:
        previous = self.last_outcome_id
        try:
            outcome_id = outcome_repository.record_outcome(
                model_id=model.id,
                provider=model.provider,
                model_tier=model.tier.value,
                stage=stage,
                outcome=outcome,
                success=success,
                request_id=self.context.request_id,
                task_type=self.context.task_type,
                difficulty=self.context.difficulty,
                error_code=error_code,
                latency_ms=latency_ms,
                estimated_cost=estimated_cost,
            )
            if stage != STAGE_GENERATION and previous is not None:
                outcome_repository.mark_fallback_used(previous)
        except Exception as exc:  # noqa: BLE001 — feedback must never fail a request
            logger.warning(
                "[request_id=%s] Failed to record outcome for model=%s: %s",
                self.context.request_id,
                model.id,
                exc,
            )
            return None
        self.last_outcome_id = outcome_id
        return outcome_id

    def attach_quality(self, outcome_id: int | None, quality: float | None, *, quality_failure: bool) -> None:
        if outcome_id is None or quality is None:
            return
        try:
            outcome_repository.set_quality(outcome_id, quality, quality_failure=quality_failure)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[request_id=%s] Failed to record quality for outcome %s: %s",
                self.context.request_id,
                outcome_id,
                exc,
            )
