"""Rule-based adaptive router."""

from __future__ import annotations

from typing import Any

from app.config.settings import Settings, get_settings
from app.models.registry import get_model_registry
from app.router.base import Router
from app.router.capabilities import requirements_from_configuration
from app.router.constraints import constraints_from_configuration, preferred_model_from_configuration
from app.router.difficulty import estimate_difficulty
from app.router.features import extract_features
from app.router.policy import (
    build_explanation_bullets,
    evaluate_tiers,
    get_policy_config,
    resolve_preferred_model,
    select_model_from_evaluations,
)
from app.router.task_classifier import classify_task
from app.schemas.routing import RouteRequest, RoutingDecision, TierQualityEstimate


class RuleBasedRouter(Router):
    """Baseline router using prompt features, task type, and quality/cost policy."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.registry = get_model_registry()

    def route(self, request: RouteRequest, configuration: dict[str, Any] | None = None) -> RoutingDecision:
        policy = get_policy_config(self.settings)
        if configuration:
            if "quality_floor" in configuration:
                policy.quality_floor = float(configuration["quality_floor"])
            if "cost_priority" in configuration:
                policy.cost_priority = float(configuration["cost_priority"])
            if "latency_priority" in configuration:
                policy.latency_priority = float(configuration["latency_priority"])

        requirements = requirements_from_configuration(configuration)
        constraints = constraints_from_configuration(configuration)
        preferred_model_id = preferred_model_from_configuration(configuration)

        features = extract_features(request.prompt)
        task_type, task_confidence = classify_task(features)
        difficulty = estimate_difficulty(features, task_type)
        evaluations = evaluate_tiers(
            prompt=request.prompt,
            task_type=task_type,
            difficulty=difficulty,
            registry=self.registry,
            policy=policy,
            requirements=requirements,
            constraints=constraints,
        )

        preferred_eval, preferred_reason = None, None
        if preferred_model_id:
            preferred_eval, preferred_reason = resolve_preferred_model(
                preferred_model_id,
                self.registry,
                request.prompt,
                task_type,
                difficulty,
                policy,
                requirements,
                constraints,
            )

        if preferred_eval is not None:
            selected = preferred_eval
        else:
            selected = select_model_from_evaluations(
                evaluations, policy, requirements=requirements, constraints=constraints
            )

        if not selected.model:
            raise ValueError("No model available for routing.")

        strong_eval = next((item for item in evaluations if item.tier.value == "strong" and item.model), None)
        strong_cost = strong_eval.estimated_cost if strong_eval else selected.estimated_cost
        cost_saved = round(max(0.0, strong_cost - selected.estimated_cost), 8)

        tier_qualities = [
            TierQualityEstimate(
                tier=item.tier.value,
                model_id=item.model.id if item.model else None,
                expected_quality=item.expected_quality,
                estimated_cost=item.estimated_cost,
                meets_quality_floor=item.meets_quality_floor,
            )
            for item in evaluations
            if item.model
        ]

        explanation_bullets = build_explanation_bullets(
            task_type=task_type,
            difficulty=difficulty,
            policy=policy,
            evaluations=evaluations,
            selected=selected,
            requirements=requirements,
            constraints=constraints,
            preferred_model_id=preferred_model_id,
            preferred_model_reason=preferred_reason,
        )

        if features.has_code:
            explanation_bullets.insert(2, "Code detected: Yes")
        if features.reasoning_score >= 0.4:
            explanation_bullets.insert(
                3,
                f"Multi-step reasoning: {'High' if features.reasoning_score >= 0.7 else 'Moderate'}",
            )

        reason = explanation_bullets[-1]
        routing_confidence = round(min(0.99, (task_confidence + (1 - abs(difficulty - 0.5))) / 2), 2)

        return RoutingDecision(
            selected_model=selected.model.id,
            model_tier=selected.tier.value,
            confidence=routing_confidence,
            difficulty=difficulty,
            task_type=task_type.value,
            reason=reason,
            estimated_cost=selected.estimated_cost,
            estimated_quality=selected.expected_quality,
            strong_model_baseline_cost=strong_cost,
            cost_saved_vs_strong=cost_saved,
            explanation=explanation_bullets,
            tier_qualities=tier_qualities,
            features={
                "prompt_length": features.prompt_length,
                "word_count": features.word_count,
                "has_code": features.has_code,
                "has_math": features.has_math,
                "instruction_count": features.instruction_count,
                "reasoning_score": features.reasoning_score,
                "requested_output_format": features.requested_output_format,
            },
            preferred_model=preferred_model_id,
            preferred_model_honored=(preferred_eval is not None) if preferred_model_id else None,
        )
