"""Per-model provider health tracking and circuit breaking.

Circuit state machine, per model_id:

    CLOSED --[consecutive retryable failures >= threshold]--> OPEN
    OPEN --[cooldown elapsed, one caller claims the trial]--> HALF_OPEN
    HALF_OPEN --[trial succeeds]--> CLOSED
    HALF_OPEN --[trial fails]--> OPEN (cooldown restarts)

A model that has never recorded an outcome has no row and is treated as CLOSED
(healthy) by default — this is what makes the feature invisible when everything is
healthy (no health rows exist until something actually fails).

Two different entry points are exposed deliberately:

- `is_routable()` is a **read-only** check used by routing/tier-selection
  (app/router/policy.py) to decide eligibility for many candidate tiers at once,
  including ones that won't necessarily be attempted. It must never itself consume
  the single half-open trial slot — only an actual generation attempt should do that.
- `check_and_claim_for_generation()` is the **mutating** check used immediately before
  an actual `provider.generate()` call (app/services/fallback.py). This is where an
  OPEN circuit whose cooldown has elapsed is atomically flipped to HALF_OPEN for the
  one caller that gets to run the trial request.

Provider vs. model level: health is tracked per model_id (not per provider), per the
task's guidance to prefer model-level granularity. A single model going down (e.g. one
Gemini model returning 500s) does not mark every other model from the same provider
unhealthy — each model_id gets its own independent circuit.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum

from app.config.settings import Settings, get_settings
from app.db import health_repository


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class HealthConfig:
    failure_threshold: int = 3
    cooldown_seconds: float = 30.0


def get_health_config(settings: Settings | None = None) -> HealthConfig:
    cfg = settings or get_settings()
    return HealthConfig(
        failure_threshold=cfg.health_failure_threshold,
        cooldown_seconds=cfg.health_cooldown_seconds,
    )


def _iso(epoch: float | None) -> str | None:
    if epoch is None:
        return None
    return datetime.fromtimestamp(epoch, tz=UTC).isoformat()


@dataclass
class ModelHealthSnapshot:
    model_id: str
    provider: str
    state: CircuitState
    consecutive_failures: int
    recent_failures: int
    recent_successes: int
    opened_at: str | None
    last_success: str | None
    last_failure: str | None
    last_error: str | None
    cooldown_remaining_seconds: float | None

    @classmethod
    def from_row(cls, row: dict, config: HealthConfig) -> "ModelHealthSnapshot":
        state = CircuitState(row["state"])
        remaining = None
        if state == CircuitState.OPEN and row["opened_at"] is not None:
            remaining = max(0.0, config.cooldown_seconds - (time.time() - row["opened_at"]))
        return cls(
            model_id=row["model_id"],
            provider=row["provider"],
            state=state,
            consecutive_failures=row["consecutive_failures"],
            recent_failures=row["recent_failures"],
            recent_successes=row["recent_successes"],
            opened_at=_iso(row["opened_at"]),
            last_success=_iso(row["last_success"]),
            last_failure=_iso(row["last_failure"]),
            last_error=row["last_error"],
            cooldown_remaining_seconds=remaining,
        )

    @classmethod
    def default_closed(cls, model_id: str, provider: str) -> "ModelHealthSnapshot":
        """A model with no recorded outcomes yet: healthy by default."""
        return cls(
            model_id=model_id,
            provider=provider,
            state=CircuitState.CLOSED,
            consecutive_failures=0,
            recent_failures=0,
            recent_successes=0,
            opened_at=None,
            last_success=None,
            last_failure=None,
            last_error=None,
            cooldown_remaining_seconds=None,
        )


def get_model_health(model_id: str, provider: str, config: HealthConfig | None = None) -> ModelHealthSnapshot:
    config = config or get_health_config()
    row = health_repository.get_health(model_id)
    if row is None:
        return ModelHealthSnapshot.default_closed(model_id, provider)
    return ModelHealthSnapshot.from_row(row, config)


def list_model_health(models: list[tuple[str, str]], config: HealthConfig | None = None) -> list[ModelHealthSnapshot]:
    """Health for a given list of (model_id, provider) pairs — typically every
    registered model, so models that have never failed are still reported as healthy."""
    config = config or get_health_config()
    rows_by_id = {row["model_id"]: row for row in health_repository.list_health()}
    snapshots = []
    for model_id, provider in models:
        row = rows_by_id.get(model_id)
        if row is None:
            snapshots.append(ModelHealthSnapshot.default_closed(model_id, provider))
        else:
            snapshots.append(ModelHealthSnapshot.from_row(row, config))
    return snapshots


def _cooldown_elapsed(row: dict, config: HealthConfig) -> bool:
    return row["opened_at"] is not None and (time.time() - row["opened_at"]) >= config.cooldown_seconds


def _cooldown_message(model_id: str, row: dict, config: HealthConfig) -> str:
    if row["opened_at"] is None:
        return f"model '{model_id}' is temporarily unavailable"
    remaining = max(0.0, config.cooldown_seconds - (time.time() - row["opened_at"]))
    return f"model '{model_id}' is temporarily unavailable (circuit open, retry in {remaining:.0f}s)"


def is_routable(model_id: str, config: HealthConfig | None = None) -> tuple[bool, str | None]:
    """Read-only eligibility check for routing/tier-selection.

    Never claims the half-open trial slot — see module docstring. A model whose
    cooldown has already elapsed is reported as eligible here (so routing can select
    it), and the actual claim happens only in check_and_claim_for_generation().
    """
    config = config or get_health_config()
    row = health_repository.get_health(model_id)
    if row is None:
        return True, None

    state = CircuitState(row["state"])
    if state == CircuitState.CLOSED:
        return True, None
    if state == CircuitState.HALF_OPEN:
        return False, f"model '{model_id}' is currently being health-checked after a prior failure"

    # OPEN
    if _cooldown_elapsed(row, config):
        return True, None
    return False, _cooldown_message(model_id, row, config)


def acquire_for_generation(
    model_id: str,
    provider: str,
    config: HealthConfig | None = None,
) -> tuple[bool, str | None, bool]:
    """Like check_and_claim_for_generation, plus whether *this* call claimed the
    half-open trial — so a caller whose attempt ends without a verdict can release it."""
    config = config or get_health_config()
    row = health_repository.get_health(model_id)
    if row is None:
        return True, None, False

    state = CircuitState(row["state"])
    if state == CircuitState.CLOSED:
        return True, None, False
    if state == CircuitState.HALF_OPEN:
        return False, f"model '{model_id}' is currently being health-checked after a prior failure", False

    # OPEN: only one caller may claim the trial.
    if not _cooldown_elapsed(row, config):
        return False, _cooldown_message(model_id, row, config), False

    claimed = health_repository.try_transition_to_half_open(model_id, config.cooldown_seconds)
    if claimed:
        return True, None, True
    return False, f"model '{model_id}' is currently being health-checked after a prior failure", False


def check_and_claim_for_generation(
    model_id: str,
    provider: str,
    config: HealthConfig | None = None,
) -> tuple[bool, str | None]:
    """Mutating availability check used immediately before an actual generation call.

    Atomically transitions OPEN -> HALF_OPEN (claiming the single trial slot) when the
    cooldown has elapsed. If another caller already claimed it, or the circuit is
    already HALF_OPEN, this returns unavailable rather than allowing a second
    concurrent trial through.
    """
    available, reason, _claimed = acquire_for_generation(model_id, provider, config)
    return available, reason


def release_trial(model_id: str) -> None:
    """Hand back a half-open trial that ended without a success/failure verdict."""
    health_repository.release_half_open_trial(model_id)


def record_success(model_id: str, provider: str) -> None:
    health_repository.record_success(model_id, provider)


def record_failure(model_id: str, provider: str, error: str, config: HealthConfig | None = None) -> str:
    config = config or get_health_config()
    return health_repository.record_failure(model_id, provider, error, failure_threshold=config.failure_threshold)
