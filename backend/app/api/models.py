"""Model registry API endpoints."""

from fastapi import APIRouter, HTTPException, status

from app.models.registry import get_model_registry
from app.schemas.models import ModelCreateRequest, ModelMetadata, ModelUpdateRequest

router = APIRouter(prefix="/api/models", tags=["models"])


@router.get("", response_model=list[ModelMetadata])
def list_models(enabled_only: bool = False) -> list[ModelMetadata]:
    registry = get_model_registry()
    return registry.list_models(enabled_only=enabled_only)


@router.get("/{model_id}", response_model=ModelMetadata)
def get_model(model_id: str) -> ModelMetadata:
    registry = get_model_registry()
    model = registry.get_model(model_id)
    if not model:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Model '{model_id}' not found")
    return model


@router.post("", response_model=ModelMetadata, status_code=status.HTTP_201_CREATED)
def create_model(request: ModelCreateRequest) -> ModelMetadata:
    registry = get_model_registry()
    try:
        return registry.add_model(request)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.patch("/{model_id}", response_model=ModelMetadata)
def update_model(model_id: str, request: ModelUpdateRequest) -> ModelMetadata:
    registry = get_model_registry()
    try:
        return registry.update_model(model_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/{model_id}/enable", response_model=ModelMetadata)
def enable_model(model_id: str) -> ModelMetadata:
    registry = get_model_registry()
    try:
        return registry.set_enabled(model_id, enabled=True)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/{model_id}/disable", response_model=ModelMetadata)
def disable_model(model_id: str) -> ModelMetadata:
    registry = get_model_registry()
    try:
        return registry.set_enabled(model_id, enabled=False)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
