"""OpenAI-compatible API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import JSONResponse

from app.api.errors import ERROR_STATUS_MAP
from app.config.settings import Settings, get_settings
from app.models.registry import get_model_registry
from app.providers.base import ProviderError
from app.schemas.openai import (
    OpenAIChatCompletionRequest,
    OpenAIErrorDetail,
    OpenAIErrorResponse,
    OpenAIModel,
)
from app.services.chat import get_chat_service
from app.utils.openai_compat import (
    AUTO_MODEL,
    to_chat_request,
    to_openai_model,
    to_openai_model_list,
    to_openai_response,
)

router = APIRouter(prefix="/v1", tags=["openai-compatible"])


def verify_router_api_key(
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    """Optional bearer-token auth when ROUTER_API_KEY is configured."""
    if not settings.router_api_key:
        return
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header.",
        )
    token = authorization.removeprefix("Bearer ").strip()
    if token != settings.router_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key.",
        )


def _openai_error_response(
    message: str,
    *,
    error_type: str = "invalid_request_error",
    code: str | None = None,
    http_status: int = status.HTTP_400_BAD_REQUEST,
) -> JSONResponse:
    payload = OpenAIErrorResponse(
        error=OpenAIErrorDetail(message=message, type=error_type, code=code)
    )
    return JSONResponse(status_code=http_status, content=payload.model_dump())


def _provider_error_response(exc: ProviderError) -> JSONResponse:
    http_status = ERROR_STATUS_MAP.get(exc.code, status.HTTP_500_INTERNAL_SERVER_ERROR)
    error_type = "server_error" if http_status >= 500 else "invalid_request_error"
    return _openai_error_response(exc.message, error_type=error_type, http_status=http_status)


@router.get("/models")
def list_models(_auth: None = Depends(verify_router_api_key)) -> dict:
    registry = get_model_registry()
    models = registry.list_models(enabled_only=True)
    return to_openai_model_list(models).model_dump()


@router.get("/models/{model_id}")
def get_model(model_id: str, _auth: None = Depends(verify_router_api_key)) -> OpenAIModel:
    if model_id == AUTO_MODEL:
        return OpenAIModel(id=AUTO_MODEL, created=0, owned_by="adaptive-router")

    registry = get_model_registry()
    model = registry.get_model(model_id)
    if not model or not model.enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Model '{model_id}' not found.")
    return to_openai_model(model)


@router.post("/chat/completions", response_model=None)
async def create_chat_completion(
    request: OpenAIChatCompletionRequest,
    x_quality_floor: float | None = Header(default=None, alias="X-Quality-Floor"),
    _auth: None = Depends(verify_router_api_key),
) -> JSONResponse:
    """OpenAI-compatible chat completions with adaptive routing via model='auto'."""
    if request.stream:
        return _openai_error_response(
            "Streaming is not supported. Set stream=false or omit the stream field.",
            code="streaming_not_supported",
        )

    try:
        chat_request = to_chat_request(request, quality_floor=x_quality_floor)
    except ValueError as exc:
        return _openai_error_response(str(exc))

    service = get_chat_service()
    try:
        chat_response = await service.chat(chat_request)
    except ProviderError as exc:
        return _provider_error_response(exc)

    return JSONResponse(content=to_openai_response(chat_response).model_dump())
