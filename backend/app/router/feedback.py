"""Closing the loop: let judged outcomes correct the router's quality expectations.

The registry's `quality_score` is a hand-set prior. Once a model has judged outcomes for a
task type, routing blends what was measured with that prior, so a model that turns out to be
weak at, say, debugging is trusted less for it, and one that beats its prior is trusted more.

    observed  = mean judged quality, moved to this prompt's difficulty
                (mean_quality + penalty(mean_difficulty) - penalty(difficulty))
    estimate  = (prior * PRIOR_WEIGHT + observed * n) / (PRIOR_WEIGHT + n)

With no data (n < MIN_SAMPLES) the prior is returned untouched, so a fresh deployment routes
exactly as before. Limitation: a model that stops being chosen stops producing evidence, so
a bad early streak is not automatically re-examined; exploration is a separate feature.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from app.config.settings import get_settings
from app.db import outcome_repository
from app.schemas.models import ModelTier

MIN_SAMPLES = 10
PRIOR_WEIGHT = 20
CACHE_TTL_SECONDS = 30.0


@dataclass(frozen=True)
class TaskQuality:
    scored_count: int
    mean_quality: float
    mean_difficulty: float


_cache: dict | None = None


def _stats() -> dict[tuple[str, str], TaskQuality]:
    """Per-(model, task) statistics, cached briefly and refreshed after any outcome write.
    Keyed on the database too, so a different DB (tests, another deployment) never reads
    another one's numbers."""
    global _cache
    key = (get_settings().database_url, outcome_repository.write_version())
    if _cache and _cache["key"] == key and time.monotonic() - _cache["at"] < CACHE_TTL_SECONDS:
        return _cache["data"]
    try:
        rows = outcome_repository.task_quality_stats()
    except Exception:  # noqa: BLE001 — routing must never fail because feedback is unavailable
        return {}
    data = {
        (row["model_id"], row["task_type"]): TaskQuality(
            int(row["scored_count"]), float(row["mean_quality"]), float(row["mean_difficulty"])
        )
        for row in rows
    }
    _cache = {"key": key, "at": time.monotonic(), "data": data}
    return data


def reset_cache() -> None:
    global _cache
    _cache = None


def blend_quality(
    prior: float,
    tier: ModelTier,
    difficulty: float,
    observed: TaskQuality | None,
    *,
    min_samples: int = MIN_SAMPLES,
    prior_weight: int = PRIOR_WEIGHT,
) -> tuple[float, int]:
    """Return (quality estimate, samples used). Pure, so it is easy to test."""
    from app.router.policy import difficulty_penalty  # local: policy imports this module

    if observed is None or observed.scored_count < min_samples:
        return prior, 0
    at_this_difficulty = (
        observed.mean_quality
        + difficulty_penalty(tier, observed.mean_difficulty)
        - difficulty_penalty(tier, difficulty)
    )
    n = observed.scored_count
    blended = (prior * prior_weight + at_this_difficulty * n) / (prior_weight + n)
    return min(max(blended, 0.0), 1.0), n


def measured_quality(model_id: str, task_type: str) -> TaskQuality | None:
    return _stats().get((model_id, task_type))
