"""Central cost calculation utilities."""

from app.schemas.chat import CostBreakdown
from app.schemas.models import ModelMetadata


def calculate_cost(
    input_tokens: int,
    output_tokens: int,
    model: ModelMetadata,
) -> CostBreakdown:
    """Calculate input, output, and total cost from token counts and model pricing."""
    input_cost = (input_tokens / 1_000_000) * model.input_cost_per_1m_tokens
    output_cost = (output_tokens / 1_000_000) * model.output_cost_per_1m_tokens
    total_cost = input_cost + output_cost
    return CostBreakdown(
        input_cost=round(input_cost, 8),
        output_cost=round(output_cost, 8),
        total_cost=round(total_cost, 8),
    )
