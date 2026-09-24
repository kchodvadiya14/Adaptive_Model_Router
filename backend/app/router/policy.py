"""Configurable routing policy for quality/cost trade-offs."""

from __future__ import annotations

from dataclasses import dataclass

from app.config.settings import Settings, get_settings
from app.models.registry import ModelRegistry, get_model_registry
from app.router.capabilities import (
    CapabilityExclusion,
    CapabilityRequirements,
    NoCapableModelError,
    model_meets_capabilities,
)
from app.router.constraints import RoutingConstraints, model_meets_constraints
from app.router.difficulty import difficulty_label
from app.router.feedback import blend_quality, measured_quality
from app.router.health import is_routable
from app.router.task_classifier import TASK_CAPABILITY_MAP, TaskType
from app.schemas.models import ModelMetadata, ModelTier
from app.utils.tokens import estimate_tokens


@dataclass
class RoutingPolicyConfig:
    quality_floor: float = 0.90
    cost_priority: float = 0.7
    latency_priority: float = 0.3


@dataclass
class TierEvaluation:
    tier: ModelTier
    model: ModelMetadata | None
    expected_quality: float
    estimated_cost: float
    estimated_latency_ms: float
    meets_quality_floor: bool
    # Judged outcomes (for this model and task type) that shaped expected_quality; 0 means
    # it is still the registry's hand-set assumption.
    quality_samples: int = 0
    # Hard capability eligibility (context window / vision / tools) — independent of
    # meets_quality_floor. A tier that fails this is never selectable, regardless of
    # cost or quality; see app/router/capabilities.py.
    capability_eligible: bool = True
    capability_reason: str | None = None
    # Hard health eligibility (circuit breaker) — a tier whose model's circuit is
    # currently open is never selectable either, independent of everything else;
    # see app/router/health.py.
    health_eligible: bool = True
    health_reason: str | None = None
    # Hard per-request max_cost / max_latency_ms eligibility; see
    # app/router/constraints.py.
    constraint_eligible: bool = True
    constraint_reason: str | None = None

    @property
    def eligible(self) -> bool:
        return self.capability_eligible and self.health_eligible and self.constraint_eligible

    @property
    def ineligibility_reason(self) -> str | None:
        """The first failing hard filter, in the order they are applied."""
        if not self.capability_eligible:
            return self.capability_reason
        if not self.health_eligible:
            return self.health_reason
        if not self.constraint_eligible:
            return self.constraint_reason
        return None


class PreferredModelUnavailableError(ValueError):
    """The requested preferred_model does not exist or is disabled."""

    def __init__(self, model_id: str, reason: str) -> None:
        super().__init__(f"Preferred model '{model_id}' {reason}.")
        self.model_id = model_id
        self.reason = reason


def get_policy_config(settings: Settings | None = None) -> RoutingPolicyConfig:
    cfg = settings or get_settings()
    return RoutingPolicyConfig(
        quality_floor=cfg.quality_floor,
        cost_priority=cfg.cost_priority,
        latency_priority=cfg.latency_priority,
    )


def _capability_boost(task_type: TaskType, model: ModelMetadata) -> float:
    required = TASK_CAPABILITY_MAP.get(task_type, ["general"])
    overlap = sum(1 for cap in required if cap in model.capabilities or "general" in model.capabilities)
    if overlap == 0:
        return -0.08
    return min(0.06, overlap * 0.03)


def difficulty_penalty(tier: ModelTier, difficulty: float) -> float:
    """How much a prompt's difficulty is assumed to cost a tier in quality."""
    return difficulty * (0.18 if tier == ModelTier.SMALL else 0.10 if tier == ModelTier.MEDIUM else 0.05)


def estimate_quality_with_evidence(
    model: ModelMetadata,
    task_type: TaskType,
    difficulty: float,
) -> tuple[float, int]:
    """Expected quality and how many judged outcomes it rests on (0 = assumption only)."""
    capability_adjustment = _capability_boost(task_type, model)
    prior = model.quality_score + capability_adjustment - difficulty_penalty(model.tier, difficulty)
    quality, samples = blend_quality(
        prior, model.tier, difficulty, measured_quality(model.id, task_type.value)
    )
    return round(min(max(quality, 0.0), 1.0), 2), samples


def estimate_quality_for_model(
    model: ModelMetadata,
    task_type: TaskType,
    difficulty: float,
) -> float:
    """Estimate expected response quality for a model on this task."""
    return estimate_quality_with_evidence(model, task_type, difficulty)[0]


def estimate_prompt_cost(model: ModelMetadata, prompt: str, expected_output_tokens: int = 256) -> float:
    input_tokens = estimate_tokens(prompt)
    input_cost = (input_tokens / 1_000_000) * model.input_cost_per_1m_tokens
    output_cost = (expected_output_tokens / 1_000_000) * model.output_cost_per_1m_tokens
    return round(input_cost + output_cost, 8)


def evaluate_model(
    model: ModelMetadata,
    prompt: str,
    task_type: TaskType,
    difficulty: float,
    policy: RoutingPolicyConfig,
    requirements: CapabilityRequirements | None = None,
    constraints: RoutingConstraints | None = None,
) -> TierEvaluation:
    """Score one model and apply every hard eligibility filter to it."""
    capability_eligible, capability_reason = model_meets_capabilities(model, requirements)
    # Read-only: previewing/selecting a model never claims a half-open trial slot —
    # only an actual generation attempt does that (app/services/fallback.py).
    health_eligible, health_reason = is_routable(model.id)
    expected_quality, quality_samples = estimate_quality_with_evidence(model, task_type, difficulty)
    estimated_cost = estimate_prompt_cost(model, prompt)
    constraint_eligible, constraint_reason = model_meets_constraints(model, estimated_cost, constraints)
    return TierEvaluation(
        tier=model.tier,
        model=model,
        expected_quality=expected_quality,
        estimated_cost=estimated_cost,
        estimated_latency_ms=model.avg_latency_ms,
        meets_quality_floor=expected_quality >= policy.quality_floor,
        quality_samples=quality_samples,
        capability_eligible=capability_eligible,
        capability_reason=capability_reason,
        health_eligible=health_eligible,
        health_reason=health_reason,
        constraint_eligible=constraint_eligible,
        constraint_reason=constraint_reason,
    )


def evaluate_tiers(
    prompt: str,
    task_type: TaskType,
    difficulty: float,
    registry: ModelRegistry | None = None,
    policy: RoutingPolicyConfig | None = None,
    requirements: CapabilityRequirements | None = None,
    constraints: RoutingConstraints | None = None,
) -> list[TierEvaluation]:
    registry = registry or get_model_registry()
    policy = policy or get_policy_config()

    evaluations: list[TierEvaluation] = []
    for tier in (ModelTier.SMALL, ModelTier.MEDIUM, ModelTier.STRONG):
        model = registry.get_primary_model_for_tier(tier)
        if not model:
            evaluations.append(
                TierEvaluation(
                    tier=tier,
                    model=None,
                    expected_quality=0.0,
                    estimated_cost=0.0,
                    estimated_latency_ms=0.0,
                    meets_quality_floor=False,
                )
            )
            continue
        evaluations.append(
            evaluate_model(model, prompt, task_type, difficulty, policy, requirements, constraints)
        )
    return evaluations


def filter_eligible_tiers(
    evaluations: list[TierEvaluation],
    requirements: CapabilityRequirements | None = None,
    constraints: RoutingConstraints | None = None,
) -> list[TierEvaluation]:
    """Hard filter: drop tiers that can't satisfy the request's capabilities, whose
    model's circuit is currently open, or that break the request's max_cost /
    max_latency_ms. Applied before any cost/quality/latency comparison. Raises
    ``NoCapableModelError`` (a ``ValueError``) with a per-tier explanation if nothing
    qualifies.
    """
    any_model = [item for item in evaluations if item.model]
    if not any_model:
        raise ValueError("No enabled models available for routing.")

    eligible = [item for item in any_model if item.eligible]
    if not eligible:
        exclusions = [
            CapabilityExclusion(
                tier=item.tier.value,
                model_id=item.model.id,
                model_name=item.model.name,
                reason=item.ineligibility_reason or "does not meet the request's requirements",
            )
            for item in any_model
        ]
        raise NoCapableModelError(requirements or CapabilityRequirements(), exclusions, constraints)
    return eligible


def select_model_from_evaluations(
    evaluations: list[TierEvaluation],
    policy: RoutingPolicyConfig,
    requirements: CapabilityRequirements | None = None,
    constraints: RoutingConstraints | None = None,
) -> TierEvaluation:
    """Select the best tier meeting the quality floor using cost/latency priorities.

    Capability, health and cost/latency-constraint eligibility are hard filters applied
    first: an ineligible tier is removed from consideration entirely, before
    cost/quality/latency ever get compared. None of them is merely penalized in the
    trade-off below.
    """
    capable = filter_eligible_tiers(evaluations, requirements, constraints)

    eligible = [item for item in capable if item.meets_quality_floor]
    if eligible:
        costs = [item.estimated_cost for item in eligible]
        latencies = [item.estimated_latency_ms for item in eligible]
        min_cost, max_cost = min(costs), max(costs)
        min_latency, max_latency = min(latencies), max(latencies)
        total_weight = policy.cost_priority + policy.latency_priority

        def optimization_score(item: TierEvaluation) -> float:
            if total_weight <= 0:
                return item.estimated_cost
            norm_cost = (
                0.0
                if max_cost == min_cost
                else (item.estimated_cost - min_cost) / (max_cost - min_cost)
            )
            norm_latency = (
                0.0
                if max_latency == min_latency
                else (item.estimated_latency_ms - min_latency) / (max_latency - min_latency)
            )
            return (policy.cost_priority * norm_cost + policy.latency_priority * norm_latency) / total_weight

        return min(eligible, key=optimization_score)

    return max(capable, key=lambda item: item.expected_quality)


def resolve_preferred_model(
    preferred_model_id: str,
    registry: ModelRegistry,
    prompt: str,
    task_type: TaskType,
    difficulty: float,
    policy: RoutingPolicyConfig,
    requirements: CapabilityRequirements | None = None,
    constraints: RoutingConstraints | None = None,
) -> tuple[TierEvaluation | None, str | None]:
    """Check a preferred model against the same hard filters as every other candidate.

    Returns (evaluation, None) when the preference can be honored, or (None, reason)
    when it is blocked by capability, health, or a cost/latency constraint — routing then
    proceeds normally among the other eligible candidates. A preferred model that does
    not exist or is disabled is a client error and raises instead.
    """
    model = registry.get_model(preferred_model_id)
    if model is None:
        raise PreferredModelUnavailableError(preferred_model_id, "was not found in the registry")
    if not model.enabled:
        raise PreferredModelUnavailableError(preferred_model_id, "is disabled")

    evaluation = evaluate_model(model, prompt, task_type, difficulty, policy, requirements, constraints)
    if evaluation.eligible:
        return evaluation, None
    return None, evaluation.ineligibility_reason


def build_explanation_bullets(
    task_type: TaskType,
    difficulty: float,
    policy: RoutingPolicyConfig,
    evaluations: list[TierEvaluation],
    selected: TierEvaluation,
    requirements: CapabilityRequirements | None = None,
    constraints: RoutingConstraints | None = None,
    preferred_model_id: str | None = None,
    preferred_model_reason: str | None = None,
) -> list[str]:
    bullets = [
        f"Task type: {task_type.value.replace('_', ' ').title()}",
        f"Difficulty: {difficulty_label(difficulty).title()} ({difficulty:.2f})",
        f"Quality requirement: {policy.quality_floor:.0%}",
    ]

    if requirements and requirements.is_active():
        bullets.append(f"Capability requirement: {requirements.describe()}")
    if constraints and constraints.is_active():
        bullets.append(f"Request constraint: {constraints.describe()}")

    capability_excluded = [item for item in evaluations if item.model and not item.capability_eligible]
    for item in capability_excluded:
        bullets.append(
            f"{item.tier.value.title()} tier excluded: '{item.model.name}' {item.capability_reason}"
        )

    health_excluded = [
        item for item in evaluations if item.model and item.capability_eligible and not item.health_eligible
    ]
    for item in health_excluded:
        bullets.append(f"{item.tier.value.title()} tier excluded: {item.health_reason}")

    constraint_excluded = [
        item
        for item in evaluations
        if item.model and item.capability_eligible and item.health_eligible and not item.constraint_eligible
    ]
    for item in constraint_excluded:
        bullets.append(
            f"{item.tier.value.title()} tier excluded: '{item.model.name}' {item.constraint_reason}"
        )

    for item in evaluations:
        if not item.model or not item.eligible:
            continue
        status = "meets floor" if item.meets_quality_floor else "below floor"
        basis = (
            f"measured on {item.quality_samples} judged {task_type.value.replace('_', ' ')} outcomes"
            if item.quality_samples
            else "assumed, no judged outcomes yet"
        )
        bullets.append(
            f"Expected {item.tier.value} model quality: {item.expected_quality:.2f} ({status}; {basis})"
        )

    preferred_honored = bool(
        preferred_model_id and selected.model and selected.model.id == preferred_model_id and preferred_model_reason is None
    )

    if preferred_model_id and not preferred_honored:
        bullets.append(f"Preferred model '{preferred_model_id}' not used: {preferred_model_reason}")

    if preferred_honored:
        floor_note = (
            "meets the quality requirement"
            if selected.meets_quality_floor
            else f"expected quality {selected.expected_quality:.2f} is below the quality requirement"
        )
        bullets.append(
            f"Preferred model '{selected.model.name}' selected as requested: it passes capability, "
            f"health and constraint checks ({floor_note})"
        )
        return bullets

    if capability_excluded and selected.eligible:
        excluded_tiers = ", ".join(item.tier.value for item in capability_excluded)
        bullets.append(
            f"{selected.tier.value.title()} tier selected because the request requires "
            f"{requirements.describe()} and the {excluded_tiers} tier(s) do not support it"
        )
    elif health_excluded and selected.eligible:
        excluded_tiers = ", ".join(item.tier.value for item in health_excluded)
        bullets.append(
            f"{selected.tier.value.title()} tier selected because the {excluded_tiers} tier(s) "
            f"are temporarily unavailable"
        )
    elif constraint_excluded and selected.eligible:
        excluded_tiers = ", ".join(item.tier.value for item in constraint_excluded)
        bullets.append(
            f"{selected.tier.value.title()} tier selected because the {excluded_tiers} tier(s) "
            f"break the request constraint ({constraints.describe()})"
        )

    bullets.append(
        f"{selected.tier.value.title()} model '{selected.model.name}' is the best cost/latency trade-off "
        f"(cost priority {policy.cost_priority:.0%}, latency priority {policy.latency_priority:.0%}) "
        f"satisfying the quality requirement"
        if selected.meets_quality_floor
        else f"Strongest available model '{selected.model.name}' selected because no cheaper tier met the quality floor"
    )
    return bullets
