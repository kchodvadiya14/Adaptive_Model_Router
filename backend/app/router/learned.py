"""Learned router: predict each model's quality for *this kind of prompt* from judged history.

For every eligible model the router looks at the past prompts most similar to the incoming one
(cosine similarity of prompt embeddings) that the model actually answered and that the judge
scored, and forms a similarity-weighted quality estimate smoothed toward the registry's hand-set
prior:

    q_hat = (prior * W + sum_j w_j * q_j) / (W + sum_j w_j),     w_j = clamp((cos_j - t) / (1 - t))

A model with no similar history keeps its prior. The estimate is local to the prompt's
neighbourhood, so a model that is good at one kind of prompt and weak at another is trusted for the
first and not the second, which a single average quality score cannot express.

Selection is over *models*, not tiers: after the usual hard filters (capability, circuit health,
cost/latency limits) it takes the cheapest model whose optimistic estimate clears the quality floor,

    q_hat + exploration_bonus / sqrt(1 + evidence)  >=  floor,        evidence = sum_j w_j

The bonus fades as evidence grows, so a cheap model not yet tried on this kind of prompt still gets a
chance (and produces the evidence that settles it). If none clears the floor, the highest q_hat wins.

Three safety nets keep this honest:
  * Cold start / failure: with fewer than LEARNED_MIN_SAMPLES judged, embedded outcomes in this
    deployment (or if the encoder fails) the request is routed by the static rule-based router and
    the decision says so. A generic router is never assumed to fit a new customer.
  * Quality guard: if the judged quality customers actually received for a task type has dropped
    below the floor (by more than GUARD_TOLERANCE, over at least GUARD_MIN_SAMPLES recent
    answers), that segment stops being cost-optimised: the highest-quality eligible model is used.
  * Every decision explains its evidence and whether it was fallback, optimistic, or guarded.

Data caveat: history only contains answers from models that were chosen (bandit feedback), unlike
the full-information data of routing_lab's offline evaluation.
"""

from __future__ import annotations

import logging
import math
import threading
from dataclasses import dataclass
from typing import Any

import numpy as np

from app.config.settings import Settings, get_settings
from app.db import outcome_repository
from app.models.registry import get_model_registry
from app.router.base import Router
from app.router.capabilities import requirements_from_configuration
from app.router.constraints import constraints_from_configuration, preferred_model_from_configuration
from app.router.difficulty import estimate_difficulty
from app.router.embedder import embed_prompt, from_bytes
from app.router.features import extract_features
from app.router.policy import (
    TierEvaluation,
    build_explanation_bullets,
    estimate_prompt_cost,
    evaluate_model,
    filter_eligible_tiers,
    get_policy_config,
    resolve_preferred_model,
)
from app.router.task_classifier import classify_task
from app.schemas.models import ModelMetadata
from app.schemas.routing import RouteRequest, RoutingDecision, TierQualityEstimate

logger = logging.getLogger(__name__)


@dataclass
class ModelEstimate:
    model: ModelMetadata
    evaluation: TierEvaluation
    quality: float
    evidence: float
    optimistic: float


@dataclass
class History:
    """Per-model (embeddings, judged quality) plus recent quality per task type."""

    by_model: dict[str, tuple[np.ndarray, np.ndarray]]
    recent_by_task: dict[str, tuple[float, int]]  # task_type -> (mean judged quality, count)

    @property
    def total(self) -> int:
        return sum(len(scores) for _, scores in self.by_model.values())


class SampleIndex:
    """Rebuilt only when outcomes change (or the database differs)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._key: tuple | None = None
        self._data = History({}, {})

    def get(self, guard_window: int) -> History:
        key = (get_settings().database_url, outcome_repository.write_version(), guard_window)
        with self._lock:
            if key != self._key:
                grouped: dict[str, tuple[list[np.ndarray], list[float]]] = {}
                for model_id, blob, quality in outcome_repository.embedding_samples():
                    vectors, scores = grouped.setdefault(model_id, ([], []))
                    vectors.append(from_bytes(blob))
                    scores.append(quality)
                self._data = History(
                    {m: (np.vstack(v), np.asarray(s, dtype=np.float32)) for m, (v, s) in grouped.items()},
                    outcome_repository.recent_quality_by_task(guard_window),
                )
                self._key = key
            return self._data


_index = SampleIndex()


def predict_quality(
    prior: float,
    embedding: np.ndarray,
    samples: tuple[np.ndarray, np.ndarray] | None,
    *,
    k: int,
    prior_weight: float,
    min_similarity: float,
) -> tuple[float, float]:
    """(smoothed quality, evidence). Pure, so it can be tested without a database."""
    if samples is None or len(samples[1]) == 0:
        return prior, 0.0
    vectors, scores = samples
    similarity = vectors @ embedding
    if len(similarity) > k:
        top = np.argpartition(-similarity, k - 1)[:k]
        similarity, scores = similarity[top], scores[top]
    weights = np.clip((similarity - min_similarity) / (1.0 - min_similarity), 0.0, 1.0)
    evidence = float(weights.sum())
    quality = (prior * prior_weight + float((weights * scores).sum())) / (prior_weight + evidence)
    return min(max(quality, 0.0), 1.0), evidence


def segment_is_degraded(
    task_type: str, history: History, floor: float, *, tolerance: float, min_samples: int
) -> tuple[bool, float | None, int]:
    """(degraded?, recent mean quality, count) for a task type."""
    mean, count = history.recent_by_task.get(task_type, (None, 0))
    if mean is None or count < min_samples:
        return False, mean, count
    return mean < floor - tolerance, mean, count


class LearnedRouter(Router):
    router_type = "learned"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.registry = get_model_registry()

    # -- cold start / failure ---------------------------------------------------------------

    def _fallback(self, request: RouteRequest, configuration: dict[str, Any] | None, why: str) -> RoutingDecision:
        from app.router.rule_based import RuleBasedRouter

        decision = RuleBasedRouter(settings=self.settings).route(request, configuration)
        return decision.model_copy(
            update={
                "explanation": [f"Fallback routing (static rules): {why}", *decision.explanation],
                "features": {**decision.features, "router_type": "learned:fallback", "fallback_reason": why},
            }
        )

    # -- routing ----------------------------------------------------------------------------

    def route(self, request: RouteRequest, configuration: dict[str, Any] | None = None) -> RoutingDecision:
        settings = self.settings
        try:
            history = _index.get(settings.guard_window)
            if history.total < settings.learned_min_samples:
                return self._fallback(
                    request,
                    configuration,
                    f"only {history.total} judged, embedded outcomes in this deployment "
                    f"(needs {settings.learned_min_samples}); it has not learned your traffic yet",
                )
            embedding = embed_prompt(request.prompt)
        except Exception as exc:  # noqa: BLE001 - a routing failure must never fail the request
            logger.warning("Learned router unavailable, using fallback routing: %s", exc)
            return self._fallback(request, configuration, f"learned router unavailable ({type(exc).__name__})")
        return self._route_learned(request, configuration, history, embedding)

    def _route_learned(
        self, request: RouteRequest, configuration: dict[str, Any] | None, history: History, embedding: np.ndarray
    ) -> RoutingDecision:
        settings = self.settings
        policy = get_policy_config(settings)
        if configuration and "quality_floor" in configuration:
            policy.quality_floor = float(configuration["quality_floor"])
        requirements = requirements_from_configuration(configuration)
        constraints = constraints_from_configuration(configuration)
        preferred_model_id = preferred_model_from_configuration(configuration)

        features = extract_features(request.prompt)
        task_type, task_confidence = classify_task(features)
        difficulty = estimate_difficulty(features, task_type)

        # Every enabled model is a candidate (not one per tier), each through the same hard filters.
        evaluations = [
            evaluate_model(model, request.prompt, task_type, difficulty, policy, requirements, constraints)
            for model in self.registry.list_models(enabled_only=True)
        ]
        eligible = filter_eligible_tiers(evaluations, requirements, constraints)

        estimates: list[ModelEstimate] = []
        for evaluation in evaluations:
            if evaluation.model is None:
                continue
            quality, evidence = predict_quality(
                evaluation.expected_quality,  # the static prior for this model, task and difficulty
                embedding,
                history.by_model.get(evaluation.model.id),
                k=settings.learned_k,
                prior_weight=settings.learned_prior_weight,
                min_similarity=settings.learned_min_similarity,
            )
            evaluation.expected_quality = round(quality, 2)
            evaluation.meets_quality_floor = quality >= policy.quality_floor
            evaluation.quality_samples = int(round(evidence))
            estimates.append(
                ModelEstimate(
                    evaluation.model,
                    evaluation,
                    quality,
                    evidence,
                    quality + settings.exploration_bonus / math.sqrt(1.0 + evidence),
                )
            )
        by_id = {e.model.id: e for e in estimates}
        eligible_estimates = [by_id[item.model.id] for item in eligible]

        degraded, recent_mean, recent_n = segment_is_degraded(
            task_type.value,
            history,
            policy.quality_floor,
            tolerance=settings.guard_tolerance,
            min_samples=settings.guard_min_samples,
        )

        preferred_eval, preferred_reason = None, None
        if preferred_model_id:
            preferred_eval, preferred_reason = resolve_preferred_model(
                preferred_model_id, self.registry, request.prompt, task_type, difficulty, policy, requirements, constraints
            )
        mode = "cheapest"
        if preferred_eval is not None:
            chosen = by_id[preferred_eval.model.id]
            mode = "preferred"
        elif degraded:
            chosen = max(eligible_estimates, key=lambda e: e.quality)
            mode = "guarded"
        else:
            passing = [e for e in eligible_estimates if e.optimistic >= policy.quality_floor]
            if passing:
                chosen = min(passing, key=lambda e: (e.evaluation.estimated_cost, e.evaluation.estimated_latency_ms))
                if chosen.evaluation.meets_quality_floor is False:
                    mode = "optimistic"
            else:
                chosen = max(eligible_estimates, key=lambda e: e.quality)
                mode = "best_available"

        strong = max(estimates, key=lambda e: e.model.quality_score)
        strong_cost = estimate_prompt_cost(strong.model, request.prompt)
        selected = chosen.evaluation

        explanation = build_explanation_bullets(
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
        explanation.insert(
            0,
            f"Learned routing: quality predicted from similar past prompts, smoothed toward the registry prior "
            f"({history.total} judged samples across {len(history.by_model)} model(s)).",
        )
        if mode == "guarded":
            explanation.append(
                f"Quality guard: recent judged quality for '{task_type.value}' is {recent_mean:.2f} over {recent_n} answers, "
                f"below the {policy.quality_floor:.2f} floor; not cost-optimising this segment, using the best-estimated model."
            )
        elif mode == "optimistic":
            explanation.append(
                f"'{chosen.model.name}' is being tried on optimism: too little evidence (evidence {chosen.evidence:.1f}) "
                f"to rule it out for this kind of prompt."
            )
        elif mode == "best_available":
            explanation.append("No eligible model is expected to meet the quality floor; using the highest estimate.")

        confidence = round(min(0.99, chosen.evidence / (chosen.evidence + settings.learned_prior_weight) * 0.8 + 0.15), 2)
        return RoutingDecision(
            selected_model=chosen.model.id,
            model_tier=chosen.model.tier.value,
            confidence=confidence,
            difficulty=difficulty,
            task_type=task_type.value,
            reason=explanation[-1],
            estimated_cost=selected.estimated_cost,
            estimated_quality=round(chosen.quality, 2),
            strong_model_baseline_cost=strong_cost,
            cost_saved_vs_strong=round(max(0.0, strong_cost - selected.estimated_cost), 8),
            explanation=explanation,
            tier_qualities=[
                TierQualityEstimate(
                    tier=e.model.tier.value,
                    model_id=e.model.id,
                    expected_quality=e.evaluation.expected_quality,
                    estimated_cost=e.evaluation.estimated_cost,
                    meets_quality_floor=e.evaluation.meets_quality_floor,
                    quality_samples=e.evaluation.quality_samples,
                )
                for e in sorted(estimates, key=lambda e: e.evaluation.estimated_cost)
            ],
            features={
                "router_type": "learned",
                "mode": mode,
                "task_confidence": task_confidence,
                "evidence": {e.model.id: round(e.evidence, 2) for e in estimates},
                "segment_degraded": degraded,
            },
            preferred_model=preferred_model_id,
            preferred_model_honored=(preferred_eval is not None) if preferred_model_id else None,
        )
