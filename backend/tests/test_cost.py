"""Tests for cost calculation."""

from app.schemas.models import ModelMetadata, ModelTier, ModelType
from app.utils.cost import calculate_cost


def test_calculate_cost_basic():
    model = ModelMetadata(
        id="test",
        name="Test",
        provider="mock",
        type=ModelType.LOCAL,
        tier=ModelTier.SMALL,
        input_cost_per_1m_tokens=1.0,
        output_cost_per_1m_tokens=2.0,
        context_window=8000,
    )
    result = calculate_cost(input_tokens=1000, output_tokens=500, model=model)
    assert result.input_cost == 0.001
    assert result.output_cost == 0.001
    assert result.total_cost == 0.002


def test_calculate_cost_zero_pricing():
    model = ModelMetadata(
        id="mock",
        name="Mock",
        provider="mock",
        type=ModelType.LOCAL,
        tier=ModelTier.SMALL,
        input_cost_per_1m_tokens=0.0,
        output_cost_per_1m_tokens=0.0,
        context_window=8000,
    )
    result = calculate_cost(input_tokens=500, output_tokens=200, model=model)
    assert result.total_cost == 0.0
