"""Hard capability eligibility checks for routing.

These are gate checks, not scoring inputs: a model that fails one is removed from
consideration entirely, before cost/quality/latency are ever compared. This is
deliberately separate from ``policy.py``'s soft ``_capability_boost`` (task-keyword
overlap nudges the *quality* estimate; this module decides whether a model is even
allowed to be selected).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.router.constraints import RoutingConstraints
from app.schemas.models import ModelMetadata


@dataclass
class CapabilityRequirements:
    """What the incoming request needs a model to be able to do."""

    requires_vision: bool = False
    requires_tools: bool = False
    min_context_tokens: int = 0

    def is_active(self) -> bool:
        return self.requires_vision or self.requires_tools or self.min_context_tokens > 0

    def describe(self) -> str:
        parts: list[str] = []
        if self.requires_vision:
            parts.append("vision/image input")
        if self.requires_tools:
            parts.append("tool/function calling")
        if self.min_context_tokens > 0:
            parts.append(f"a context window of at least {self.min_context_tokens} tokens")
        return " and ".join(parts) if parts else "no special capabilities"


@dataclass
class CapabilityExclusion:
    """A tier/model that was removed from consideration and why."""

    tier: str
    model_id: str
    model_name: str
    reason: str


class NoCapableModelError(ValueError):
    """Raised when no enabled model can satisfy the request's requirements.

    Covers every hard eligibility filter: capabilities, health (circuit open), and
    per-request cost/latency constraints. `excluded` carries a per-model reason.
    """

    def __init__(
        self,
        requirements: CapabilityRequirements,
        excluded: list[CapabilityExclusion],
        constraints: RoutingConstraints | None = None,
    ) -> None:
        details = "; ".join(
            f"{item.tier} ('{item.model_name}'): {item.reason}" for item in excluded
        )
        parts: list[str] = []
        if requirements.is_active():
            parts.append(requirements.describe())
        if constraints is not None and constraints.is_active():
            parts.append(constraints.describe())
        summary = " and ".join(parts) if parts else requirements.describe()
        message = f"No enabled model meets the request's requirements ({summary})."
        if details:
            message = f"{message} {details}"
        super().__init__(message)
        self.requirements = requirements
        self.constraints = constraints
        self.excluded = excluded


def model_meets_capabilities(
    model: ModelMetadata,
    requirements: CapabilityRequirements | None,
) -> tuple[bool, str | None]:
    """Return (eligible, reason_if_not) for a single model against the requirements."""
    if requirements is None:
        return True, None
    if requirements.requires_vision and not model.supports_vision:
        return False, "does not support vision/image input"
    if requirements.requires_tools and not model.supports_tools:
        return False, "does not support tool/function calling"
    if requirements.min_context_tokens and requirements.min_context_tokens > model.context_window:
        return False, (
            f"context window ({model.context_window} tokens) is smaller than the request's "
            f"estimated {requirements.min_context_tokens} tokens"
        )
    return True, None


def requirements_from_configuration(configuration: dict[str, Any] | None) -> CapabilityRequirements | None:
    """Parse the ``required_capabilities`` entry a caller may pass via the router configuration dict.

    Mirrors how ``quality_floor``/``cost_priority`` overrides already flow through
    ``Router.route(request, configuration=...)`` — no change to the Router interface.
    """
    if not configuration:
        return None
    raw = configuration.get("required_capabilities")
    if raw is None:
        return None
    if isinstance(raw, CapabilityRequirements):
        return raw
    return CapabilityRequirements(
        requires_vision=bool(raw.get("requires_vision", False)),
        requires_tools=bool(raw.get("requires_tools", False)),
        min_context_tokens=int(raw.get("min_context_tokens", 0)),
    )
