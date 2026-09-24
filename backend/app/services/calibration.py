"""Calibrate registry quality scores against judged outcomes.

A model's registry `quality_score` is a hand-set prior. The router's expected quality for a
prompt is `quality_score + capability boost - difficulty penalty`, so a judged score observed
on prompts of some mean difficulty implies a base score of `mean_quality + difficulty penalty`.
That implied base is blended with the prior by Bayesian shrinkage: with `n` scored samples and
`prior_weight` pseudo-samples, `calibrated = (prior * prior_weight + implied * n) / (prior_weight + n)`.
A model with few samples barely moves; one with many converges on what the judge measured.

Applying is not idempotent: it blends the *current* score with the data again, so re-applying
over the same window double-counts it. Pass `since` (the previous apply time) when re-applying.

Caveat: routed traffic is not a random sample (easy prompts go to small models), and the
difficulty adjustment only partly corrects for that. A dedicated benchmark run over the same
prompts for every model gives cleaner numbers than production traffic.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.db import outcome_repository
from app.models.registry import ModelRegistry, get_model_registry
from app.router.policy import difficulty_penalty
from app.schemas.models import ModelTier, ModelUpdateRequest

DEFAULT_MIN_SAMPLES = 30
DEFAULT_PRIOR_WEIGHT = 20


class ModelCalibration(BaseModel):
    model_id: str
    tier: str | None
    scored_count: int
    mean_quality: float
    mean_difficulty: float
    implied_quality_score: float
    current_quality_score: float | None
    calibrated_quality_score: float | None
    sufficient_samples: bool


class CalibrationReport(BaseModel):
    min_samples: int
    prior_weight: int
    applied: bool
    models: list[ModelCalibration]


def calibrate(
    *,
    registry: ModelRegistry | None = None,
    min_samples: int = DEFAULT_MIN_SAMPLES,
    prior_weight: int = DEFAULT_PRIOR_WEIGHT,
    since: datetime | None = None,
    apply: bool = False,
) -> CalibrationReport:
    registry = registry or get_model_registry()
    models: list[ModelCalibration] = []
    for row in outcome_repository.calibration_stats(since=since):
        model = registry.get_model(row["model_id"])
        tier = ModelTier(model.tier) if model else (ModelTier(row["model_tier"]) if row["model_tier"] else None)
        n = int(row["scored_count"])
        penalty = difficulty_penalty(tier, row["mean_difficulty"]) if tier else 0.0
        implied = min(max(row["mean_quality"] + penalty, 0.0), 1.0)
        current = model.quality_score if model else None
        sufficient = model is not None and n >= min_samples
        calibrated = None
        if sufficient:
            calibrated = round((current * prior_weight + implied * n) / (prior_weight + n), 4)
        models.append(
            ModelCalibration(
                model_id=row["model_id"],
                tier=tier.value if tier else None,
                scored_count=n,
                mean_quality=round(row["mean_quality"], 4),
                mean_difficulty=round(row["mean_difficulty"], 4),
                implied_quality_score=round(implied, 4),
                current_quality_score=current,
                calibrated_quality_score=calibrated,
                sufficient_samples=sufficient,
            )
        )
        if apply and calibrated is not None:
            registry.update_model(row["model_id"], ModelUpdateRequest(quality_score=calibrated))
    return CalibrationReport(min_samples=min_samples, prior_weight=prior_weight, applied=apply, models=models)
