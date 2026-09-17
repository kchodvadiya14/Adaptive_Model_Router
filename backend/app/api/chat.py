"""Chat API endpoints."""

from fastapi import APIRouter, HTTPException, status

from app.api.errors import raise_provider_http_error
from app.providers.base import ProviderError
from app.router.capabilities import NoCapableModelError
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat import get_chat_service
from app.services.deadline import RequestTimeoutError

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """Send a chat completion request to a specific model."""
    service = get_chat_service()
    try:
        return await service.chat(request)
    except RequestTimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=exc.to_dict(),
            headers={"X-Request-ID": exc.request_id} if exc.request_id else None,
        ) from exc
    except NoCapableModelError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except ProviderError as exc:
        raise_provider_http_error(exc)
