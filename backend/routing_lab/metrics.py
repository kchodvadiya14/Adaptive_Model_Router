"""Cost-vs-quality metrics for routers (RouterBench-style AIQ, plus matched-quality savings).

A router is a *curve*: sweeping its cost/quality dial gives (mean cost, mean quality) points.
Everything here works on per-prompt arrays so a bootstrap over prompts can put confidence
intervals on every number.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


def upper_hull(points: np.ndarray) -> np.ndarray:
    """Non-decreasing upper concave envelope of (cost, quality) points, sorted by cost.

    This is what a router can achieve by randomly mixing its own operating points, so a
    curve is credited for the best it can do at each budget, never for a dip."""
    pts = points[np.lexsort((-points[:, 1], points[:, 0]))]
    hull: list[np.ndarray] = []
    for p in pts:
        while len(hull) >= 2:
            (x1, y1), (x2, y2) = hull[-2], hull[-1]
            if (x2 - x1) * (p[1] - y1) - (y2 - y1) * (p[0] - x1) >= 0:  # hull[-1] is under the chord
                hull.pop()
            else:
                break
        hull.append(p)
    hull = np.array(hull)
    keep = [0]
    for i in range(1, len(hull)):  # enforce non-decreasing quality
        if hull[i, 1] > hull[keep[-1], 1]:
            keep.append(i)
    return hull[keep]


def quality_at_cost(hull: np.ndarray, cost: float) -> float:
    """Quality the hull reaches at `cost` (flat beyond its ends)."""
    if cost <= hull[0, 0]:
        return float(hull[0, 1])
    if cost >= hull[-1, 0]:
        return float(hull[-1, 1])
    return float(np.interp(cost, hull[:, 0], hull[:, 1]))


def cost_for_quality(hull: np.ndarray, quality: float) -> float | None:
    """Cheapest cost at which the hull reaches `quality`; None if it never does."""
    if quality > hull[-1, 1] + 1e-12:
        return None
    if quality <= hull[0, 1]:
        return float(hull[0, 0])
    return float(np.interp(quality, hull[:, 1], hull[:, 0]))


def aiq(hull: np.ndarray, cost_lo: float, cost_hi: float, samples: int = 200) -> float:
    """Mean quality of the hull across the cost range [cost_lo, cost_hi] (higher is better).
    A shared range makes AIQ comparable between routers."""
    grid = np.linspace(cost_lo, cost_hi, samples)
    return float(np.mean([quality_at_cost(hull, c) for c in grid]))


@dataclass
class Summary:
    aiq: float
    quality_at_best_single_cost_half: float
    cost_saving_at_best_single_quality: float | None  # 1 - cost/cost_best_single at equal quality
    cost_saving_at_95pct_best_single_quality: float | None


def summarise(curve: np.ndarray, best_single: tuple[float, float], cost_lo: float, cost_hi: float) -> Summary:
    hull = upper_hull(curve)
    best_cost, best_quality = best_single
    at_quality = cost_for_quality(hull, best_quality)
    at_95 = cost_for_quality(hull, 0.95 * best_quality)
    return Summary(
        aiq=aiq(hull, cost_lo, cost_hi),
        quality_at_best_single_cost_half=quality_at_cost(hull, 0.5 * best_cost),
        cost_saving_at_best_single_quality=None if at_quality is None else 1.0 - at_quality / best_cost,
        cost_saving_at_95pct_best_single_quality=None if at_95 is None else 1.0 - at_95 / best_cost,
    )


def bootstrap(
    per_prompt_cost: np.ndarray,
    per_prompt_quality: np.ndarray,
    best_single_index: int,
    single_cost: np.ndarray,
    single_quality: np.ndarray,
    *,
    rounds: int = 500,
    seed: int = 0,
    baseline: tuple[np.ndarray, np.ndarray] | None = None,
) -> dict[str, tuple[float, float, float]]:
    """Bootstrap a router over test prompts.

    per_prompt_cost / per_prompt_quality: (n_prompts, n_operating_points) - what the router
    paid and scored on each prompt at each dial setting. single_cost / single_quality:
    (n_prompts, n_models) for the single-model baselines. Returns {metric: (mean, lo95, hi95)}.
    The best-single baseline is fixed beforehand (chosen on validation data), but its cost and
    quality are re-measured on every resample, so the comparison stays paired.
    """
    rng = np.random.default_rng(seed)
    n = per_prompt_cost.shape[0]
    cost_lo = single_cost.mean(axis=0).min()
    cost_hi = single_cost.mean(axis=0).max()
    out: dict[str, list[float]] = {"aiq": [], "saving_equal_quality": [], "saving_at_95pct": [], "aiq_uplift": []}
    for _ in range(rounds):
        idx = rng.integers(0, n, n)
        curve = np.column_stack([per_prompt_cost[idx].mean(axis=0), per_prompt_quality[idx].mean(axis=0)])
        best = (single_cost[idx, best_single_index].mean(), single_quality[idx, best_single_index].mean())
        s = summarise(curve, best, cost_lo, cost_hi)
        out["aiq"].append(s.aiq)
        if baseline is not None:  # paired: same resampled prompts for the baseline curve
            base = upper_hull(np.column_stack([baseline[0][idx].mean(axis=0), baseline[1][idx].mean(axis=0)]))
            out["aiq_uplift"].append(s.aiq - aiq(base, cost_lo, cost_hi))
        # A router that never reaches the target quality saves nothing: count that as 0, not as missing.
        out["saving_equal_quality"].append(s.cost_saving_at_best_single_quality or 0.0)
        out["saving_at_95pct"].append(s.cost_saving_at_95pct_best_single_quality or 0.0)
    return {
        k: (float(np.mean(v)), float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5)))
        for k, v in out.items()
        if v
    }
