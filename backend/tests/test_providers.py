"""Tests for provider adapters."""

import pytest

from app.providers.base import GenerationRequest, ProviderError, ProviderErrorCode
from app.providers.factory import get_provider_for_model
from app.providers.mock import MockProvider
from app.schemas.models import ModelMetadata, ModelTier, ModelType


@pytest.fixture
def mock_model() -> ModelMetadata:
    return ModelMetadata(
        id="mock-echo",
        name="Mock Echo",
        provider="mock",
        type=ModelType.LOCAL,
        tier=ModelTier.SMALL,
        input_cost_per_1m_tokens=0.0,
        output_cost_per_1m_tokens=0.0,
        context_window=32000,
    )


@pytest.mark.asyncio
async def test_mock_provider_generate(mock_model):
    provider = MockProvider(mock_model)
    assert provider.is_available() is True

    response = await provider.generate(
        GenerationRequest(messages=[{"role": "user", "content": "Hello world"}])
    )
    assert "Hello world" in response.content
    assert response.input_tokens > 0
    assert response.output_tokens > 0
    assert response.latency_ms >= 0


def test_mock_provider_estimate_cost(mock_model):
    provider = MockProvider(mock_model)
    cost = provider.estimate_cost(100, 50)
    assert cost.total_cost == 0.0


def test_get_provider_for_unknown_provider():
    model = ModelMetadata(
        id="unknown",
        name="Unknown",
        provider="nonexistent",
        type=ModelType.API,
        tier=ModelTier.SMALL,
        input_cost_per_1m_tokens=1.0,
        output_cost_per_1m_tokens=1.0,
        context_window=8000,
    )
    with pytest.raises(ProviderError) as exc:
        get_provider_for_model(model)
    assert exc.value.code == ProviderErrorCode.MODEL_UNAVAILABLE


def test_openai_provider_unavailable_without_key(mock_model):
    mock_model.provider = "openai"
    mock_model.id = "gpt-4o-mini"
    from app.providers.openai import OpenAIProvider

    provider = OpenAIProvider(mock_model)
    assert provider.is_available() is False
