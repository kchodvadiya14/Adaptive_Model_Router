"""Shared helpers for ML-based routers."""

from __future__ import annotations

from typing import Any

from app.config.settings import Settings, get_settings
from app.models.registry import get_model_registry
from app.router.base import Router
from app.router.difficulty import estimate_difficulty
from app.router.features import extract_features
from app.router.policy import (
    build_explanation_bullets,
    evaluate_tiers,
    get_policy_config,
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
        )
        selected_eval = next((item for item in evaluations if item.tier == selected_tier and item.model), None)
        if not selected_eval or not selected_eval.model:
            selected_eval = next(item for item in evaluations if item.model)

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
        )
