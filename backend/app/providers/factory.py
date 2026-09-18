"""Provider factory for resolving model adapters."""

from __future__ import annotations

from app.providers.anthropic import AnthropicProvider
from app.providers.base import BaseModelProvider, ProviderError, ProviderErrorCode
from app.providers.google import GoogleProvider
from app.providers.groq import GroqProvider
from app.providers.mock import MockProvider
from app.providers.openai import OpenAIProvider
from app.providers.openai_compatible import OpenAICompatibleProvider
from app.schemas.models import ModelMetadata

PROVIDER_CLASSES: dict[str, type[BaseModelProvider]] = {
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "google": GoogleProvider,
    "openai_compatible": OpenAICompatibleProvider,
    "groq": GroqProvider,
    "mock": MockProvider,
}


def get_provider_for_model(model: ModelMetadata) -> BaseModelProvider:
    provider_class = PROVIDER_CLASSES.get(model.provider)
    if not provider_class:
        raise ProviderError(
            f"No provider adapter registered for '{model.provider}'.",
            code=ProviderErrorCode.MODEL_UNAVAILABLE,
        )
    return provider_class(model)


def list_provider_availability(models: list[ModelMetadata]) -> dict[str, bool]:
    availability: dict[str, bool] = {}
    for model in models:
        provider = get_provider_for_model(model)
        availability[model.id] = provider.is_available()
    return availability
