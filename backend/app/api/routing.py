"""Router API endpoints."""

from fastapi import APIRouter, HTTPException, status

from app.config.settings import get_settings
from app.models.registry import get_model_registry
from app.router.base import get_router
from app.router.capabilities import NoCapableModelError
from app.router.policy import PreferredModelUnavailableError
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
        routing_threshold=settings.routing_threshold,
        judge_provider=settings.judge_provider,
        judge_model_id=settings.judge_model_id,
        evaluate_on_chat=settings.evaluate_on_chat,
        health_failure_threshold=settings.health_failure_threshold,
        health_cooldown_seconds=settings.health_cooldown_seconds,
        auth_enabled=bool(settings.router_api_key),
        configured_providers={
            "groq": bool(settings.groq_api_key),
            "google": bool(settings.google_api_key),
            "openai_compatible": bool(settings.openai_compatible_base_url and settings.openai_compatible_api_key),
            "openai": bool(settings.openai_api_key),
            "anthropic": bool(settings.anthropic_api_key),
        },
    )


@router.post("/route", response_model=RoutingDecision)
def route_prompt(request: RouteRequestWithConfig) -> RoutingDecision:
    """Analyze a prompt and return an explainable routing decision."""
    router = get_router()
    configuration = request.routing_configuration()
    try:
        return router.route(request, configuration=configuration)
    except PreferredModelUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except NoCapableModelError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
