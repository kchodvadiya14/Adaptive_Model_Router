"""Per-request cost and latency constraints for routing.

Like capability and health eligibility, these are hard filters applied before the
cost/quality/latency trade-off, not weights inside it. They only use numbers the
system already has: the same prompt-cost estimate routing already computes
(`policy.estimate_prompt_cost`) and the registry's `avg_latency_ms` metadata. No new
estimates are introduced here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.schemas.models import ModelMetadata


@dataclass
class RoutingConstraints:
    max_cost: float | None = None
    max_latency_ms: float | None = None

    def is_active(self) -> bool:
        return self.max_cost is not None or self.max_latency_ms is not None

    def describe(self) -> str:
        parts: list[str] = []
        if self.max_cost is not None:
            parts.append(f"estimated cost at most ${self.max_cost:.8f}")
        if self.max_latency_ms is not None:
            parts.append(f"average latency at most {self.max_latency_ms:.0f}ms")
        return " and ".join(parts) if parts else "no cost or latency constraints"


def model_meets_constraints(
    model: ModelMetadata,
    estimated_cost: float,
    constraints: RoutingConstraints | None,
) -> tuple[bool, str | None]:
    """Return (eligible, reason_if_not). `estimated_cost` is the caller's existing
    per-prompt estimate for this model."""
    if constraints is None:
        return True, None
    if constraints.max_cost is not None and estimated_cost > constraints.max_cost:
        return False, (
            f"estimated cost ${estimated_cost:.8f} exceeds max_cost ${constraints.max_cost:.8f}"
        )
    if constraints.max_latency_ms is not None and model.avg_latency_ms > constraints.max_latency_ms:
        return False, (
            f"average latency {model.avg_latency_ms:.0f}ms exceeds max_latency_ms "
            f"{constraints.max_latency_ms:.0f}ms"
        )
    return True, None


def constraints_from_configuration(configuration: dict[str, Any] | None) -> RoutingConstraints | None:
    """Read `max_cost` / `max_latency_ms` from the router configuration dict, the same
    channel `quality_floor` and `required_capabilities` already use."""
    if not configuration:
        return None
    max_cost = configuration.get("max_cost")
    max_latency_ms = configuration.get("max_latency_ms")
    if max_cost is None and max_latency_ms is None:
        return None
    return RoutingConstraints(
        max_cost=float(max_cost) if max_cost is not None else None,
        max_latency_ms=float(max_latency_ms) if max_latency_ms is not None else None,
    )


def preferred_model_from_configuration(configuration: dict[str, Any] | None) -> str | None:
    if not configuration:
        return None
    preferred = configuration.get("preferred_model")
    return str(preferred) if preferred else None
