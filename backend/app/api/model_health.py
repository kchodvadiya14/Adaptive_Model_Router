"""Model/provider health (circuit breaker) API endpoints."""

from fastapi import APIRouter

from app.models.registry import get_model_registry
from app.router.health import list_model_health
from app.schemas.models import ModelHealthStatus

router = APIRouter(prefix="/api/health", tags=["health"])


@router.get("/models", response_model=list[ModelHealthStatus])
def get_models_health() -> list[ModelHealthStatus]:
    """Circuit-breaker state for every registered model.

    A model that has never failed has no health record and is reported as healthy
    ('closed') by default.
    """
    registry = get_model_registry()
    models = [(model.id, model.provider) for model in registry.list_models()]
    snapshots = list_model_health(models)
    return [
        ModelHealthStatus(
            model_id=snapshot.model_id,
            provider=snapshot.provider,
            state=snapshot.state.value,
            consecutive_failures=snapshot.consecutive_failures,
            recent_failures=snapshot.recent_failures,
            recent_successes=snapshot.recent_successes,
            opened_at=snapshot.opened_at,
            last_success=snapshot.last_success,
            last_failure=snapshot.last_failure,
            last_error=snapshot.last_error,
            cooldown_remaining_seconds=snapshot.cooldown_remaining_seconds,
        )
        for snapshot in snapshots
    ]
