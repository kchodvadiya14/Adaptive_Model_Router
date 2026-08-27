"""Chat API endpoints."""

from fastapi import APIRouter

from app.api.errors import raise_provider_http_error
from app.providers.base import ProviderError
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat import get_chat_service

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """Send a chat completion request to a specific model."""
    service = get_chat_service()
    try:
        return await service.chat(request)
    except ProviderError as exc:
        raise_provider_http_error(exc)
