"""Configurable routing policy for quality/cost trade-offs."""

from __future__ import annotations

from dataclasses import dataclass

from app.config.settings import Settings, get_settings
from app.models.registry import ModelRegistry, get_model_registry
from app.router.difficulty import difficulty_label
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


def estimate_quality_for_model(
    model: ModelMetadata,
    task_type: TaskType,
    difficulty: float,
) -> float:
    """Estimate expected response quality for a model on this task."""
    capability_adjustment = _capability_boost(task_type, model)
    difficulty_penalty = difficulty * (0.18 if model.tier == ModelTier.SMALL else 0.10 if model.tier == ModelTier.MEDIUM else 0.05)
    quality = model.quality_score + capability_adjustment - difficulty_penalty
    return round(min(max(quality, 0.0), 1.0), 2)


def estimate_prompt_cost(model: ModelMetadata, prompt: str, expected_output_tokens: int = 256) -> float:
    input_tokens = estimate_tokens(prompt)
    input_cost = (input_tokens / 1_000_000) * model.input_cost_per_1m_tokens
    output_cost = (expected_output_tokens / 1_000_000) * model.output_cost_per_1m_tokens
    return round(input_cost + output_cost, 8)


def evaluate_tiers(
    prompt: str,
    task_type: TaskType,
    difficulty: float,
    registry: ModelRegistry | None = None,
    policy: RoutingPolicyConfig | None = None,
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

        expected_quality = estimate_quality_for_model(model, task_type, difficulty)
        estimated_cost = estimate_prompt_cost(model, prompt)
        evaluations.append(
            TierEvaluation(
                tier=tier,
                model=model,
                expected_quality=expected_quality,
                estimated_cost=estimated_cost,
                estimated_latency_ms=model.avg_latency_ms,
                meets_quality_floor=expected_quality >= policy.quality_floor,
            )
        )
    return evaluations


def select_model_from_evaluations(
    evaluations: list[TierEvaluation],
    policy: RoutingPolicyConfig,
) -> TierEvaluation:
    """Select the best tier meeting the quality floor using cost/latency priorities."""
    eligible = [item for item in evaluations if item.model and item.meets_quality_floor]
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

    available = [item for item in evaluations if item.model]
    if not available:
        raise ValueError("No enabled models available for routing.")

    return max(available, key=lambda item: item.expected_quality)


def build_explanation_bullets(
    task_type: TaskType,
    difficulty: float,
    policy: RoutingPolicyConfig,
    evaluations: list[TierEvaluation],
    selected: TierEvaluation,
) -> list[str]:
    bullets = [
        f"Task type: {task_type.value.replace('_', ' ').title()}",
        f"Difficulty: {difficulty_label(difficulty).title()} ({difficulty:.2f})",
        f"Quality requirement: {policy.quality_floor:.0%}",
    ]

    for item in evaluations:
        if not item.model:
            continue
        status = "meets floor" if item.meets_quality_floor else "below floor"
        bullets.append(
            f"Expected {item.tier.value} model quality: {item.expected_quality:.2f} ({status})"
        )

    bullets.append(
        f"{selected.tier.value.title()} model '{selected.model.name}' is the best cost/latency trade-off "
        f"(cost priority {policy.cost_priority:.0%}, latency priority {policy.latency_priority:.0%}) "
        f"satisfying the quality requirement"
        if selected.meets_quality_floor
        else f"Strongest available model '{selected.model.name}' selected because no cheaper tier met the quality floor"
    )
    return bullets
