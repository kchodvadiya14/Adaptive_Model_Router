"""Tests for evaluation metrics."""

from app.evaluation.metrics import (
    compute_aggregate_metrics,
    cost_reduction,
    quality_retention,
    strong_model_usage,
)


def test_cost_reduction_formula():
    assert cost_reduction(router_cost=0.002, strongest_model_cost=0.004) == 0.5


def test_quality_retention_formula():
    assert quality_retention(router_quality=0.92, strongest_model_quality=0.95) == 0.9684


def test_strong_model_usage_formula():
    assert strong_model_usage(strong_model_requests=2, total_requests=8) == 0.25


def test_compute_aggregate_metrics():
    metrics = compute_aggregate_metrics(
        qualities=[0.9, 0.85, 0.88],
        costs=[0.001, 0.002, 0.0015],
        latencies=[100, 200, 150],
        strong_baseline_costs=[0.004, 0.004, 0.004],
        strong_baseline_qualities=[0.95, 0.94, 0.96],
        selected_tiers=["small", "medium", "small"],
    )
    assert metrics.total_requests == 3
    assert metrics.cost_reduction > 0
    assert metrics.quality_retention > 0
    assert metrics.strong_model_usage == 0.0
