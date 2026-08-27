"""Router API endpoints."""

from fastapi import APIRouter, HTTPException, status

from app.config.settings import get_settings
from app.models.registry import get_model_registry
from app.router.base import get_router
from app.schemas.models import RouterStatusResponse
from app.schemas.routing import RouteRequestWithConfig, RoutingDecision

router = APIRouter(prefix="/api", tags=["router"])


@router.get("/router/status", response_model=RouterStatusResponse)
def get_router_status() -> RouterStatusResponse:
    settings = get_settings()
    registry = get_model_registry()
    all_models = registry.list_models()
    enabled_models = registry.list_models(enabled_only=True)
    return RouterStatusResponse(
        router_type=settings.router_type,
        quality_floor=settings.quality_floor,
        cost_priority=settings.cost_priority,
        latency_priority=settings.latency_priority,
        fallback_enabled=settings.fallback_enabled,
        max_fallback_attempts=settings.max_fallback_attempts,
        fallback_on_quality_below=settings.fallback_on_quality_below,
        fallback_escalation=settings.fallback_escalation,
        enabled_models=len(enabled_models),
        total_models=len(all_models),
    )


@router.post("/route", response_model=RoutingDecision)
def route_prompt(request: RouteRequestWithConfig) -> RoutingDecision:
    """Analyze a prompt and return an explainable routing decision."""
    router = get_router()
    configuration = request.configuration.model_dump(exclude_none=True) if request.configuration else None
    try:
        return router.route(request, configuration=configuration)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
