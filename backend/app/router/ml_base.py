"""Shared helpers for ML-based routers."""

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
    filter_eligible_tiers,
    get_policy_config,
    resolve_preferred_model,
)
from app.router.task_classifier import classify_task
from app.schemas.models import ModelTier
from app.schemas.routing import RouteRequest, RoutingDecision, TierQualityEstimate
from app.schemas.training import RouterTrainType
from app.training.registry import load_latest_artifact


def probability_strong_better(pipeline, prompt: str) -> float:
    probas = pipeline.predict_proba([prompt])[0]
    return float(probas[1]) if len(probas) > 1 else float(probas[0])


def tier_from_probability(prob: float, threshold: float) -> ModelTier:
    if prob >= threshold:
        return ModelTier.STRONG
    if prob >= threshold * 0.55:
        return ModelTier.MEDIUM
    return ModelTier.SMALL


class MLRouter(Router):
    router_type: RouterTrainType

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.registry = get_model_registry()
        artifact = load_latest_artifact(self.router_type)
        if not artifact:
            raise FileNotFoundError(
                f"No trained {self.router_type.value} router found. Train a model first."
            )
        self.pipeline = artifact["pipeline"]
        self.threshold = float(artifact.get("threshold", self.settings.routing_threshold))
        self.dataset_id = artifact.get("dataset_id")

    def route(self, request: RouteRequest, configuration: dict[str, Any] | None = None) -> RoutingDecision:
        policy = get_policy_config(self.settings)
        threshold = self.threshold
        if configuration:
            if "quality_floor" in configuration:
                policy.quality_floor = float(configuration["quality_floor"])
            if "routing_threshold" in configuration:
                threshold = float(configuration["routing_threshold"])

        requirements = requirements_from_configuration(configuration)
        constraints = constraints_from_configuration(configuration)
        preferred_model_id = preferred_model_from_configuration(configuration)

        features = extract_features(request.prompt)
        task_type, task_confidence = classify_task(features)
        difficulty = estimate_difficulty(features, task_type)
        prob = probability_strong_better(self.pipeline, request.prompt)
        selected_tier = tier_from_probability(prob, threshold)

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
            selected_eval = preferred_eval
        else:
            # Hard capability + health + constraint filter first (see
            # policy.filter_eligible_tiers), then the model's predicted tier, then the first
            # remaining eligible tier (same order-based fallback as before filtering existed).
            capable = filter_eligible_tiers(evaluations, requirements, constraints)
            selected_eval = next((item for item in capable if item.tier == selected_tier), None)
            if not selected_eval:
                selected_eval = capable[0]

        strong_eval = next((item for item in evaluations if item.tier == ModelTier.STRONG and item.model), None)
        strong_cost = strong_eval.estimated_cost if strong_eval else selected_eval.estimated_cost

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

        explanation = build_explanation_bullets(
            task_type=task_type,
            difficulty=difficulty,
            policy=policy,
            evaluations=evaluations,
            selected=selected_eval,
            requirements=requirements,
            constraints=constraints,
            preferred_model_id=preferred_model_id,
            preferred_model_reason=preferred_reason,
        )
        explanation.insert(
            0,
            f"ML router ({self.router_type.value}) probability strong is better: {prob:.2f}",
        )
        explanation.insert(1, f"Routing threshold: {threshold:.2f}")

        routing_confidence = round(min(0.99, (task_confidence + prob) / 2), 2)

        return RoutingDecision(
            selected_model=selected_eval.model.id,
            model_tier=selected_eval.tier.value,
            confidence=routing_confidence,
            difficulty=difficulty,
            task_type=task_type.value,
            reason=explanation[-1],
            estimated_cost=selected_eval.estimated_cost,
            estimated_quality=selected_eval.expected_quality,
            strong_model_baseline_cost=strong_cost,
            cost_saved_vs_strong=round(max(0.0, strong_cost - selected_eval.estimated_cost), 8),
            explanation=explanation,
            tier_qualities=tier_qualities,
            features={
                **features.__dict__,
                "probability_strong_better": prob,
                "router_type": self.router_type.value,
            },
            preferred_model=preferred_model_id,
            preferred_model_honored=(preferred_eval is not None) if preferred_model_id else None,
        )
