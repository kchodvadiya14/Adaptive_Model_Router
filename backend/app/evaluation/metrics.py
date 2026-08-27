"""Central evaluation metrics."""

from __future__ import annotations

from app.schemas.evaluation import AggregateMetrics


def cost_reduction(router_cost: float, strongest_model_cost: float) -> float:
    if strongest_model_cost <= 0:
        return 0.0
    return round(1 - router_cost / strongest_model_cost, 4)


def quality_retention(router_quality: float, strongest_model_quality: float) -> float:
    if strongest_model_quality <= 0:
        return 0.0
    return round(router_quality / strongest_model_quality, 4)


def strong_model_usage(strong_model_requests: int, total_requests: int) -> float:
    if total_requests <= 0:
        return 0.0
    return round(strong_model_requests / total_requests, 4)


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    index = int(round((pct / 100) * (len(sorted_values) - 1)))
    return round(sorted_values[index], 2)


def compute_aggregate_metrics(
    qualities: list[float],
    costs: list[float],
    latencies: list[float],
    strong_baseline_costs: list[float],
    strong_baseline_qualities: list[float],
    selected_tiers: list[str],
    optimal_tiers: list[str] | None = None,
) -> AggregateMetrics:
    total = len(costs)
    if total == 0:
        return AggregateMetrics(
            total_requests=0,
            average_quality=0.0,
            average_cost=0.0,
            total_cost=0.0,
            cost_reduction=0.0,
            quality_retention=0.0,
            routing_accuracy=0.0,
            strong_model_usage=0.0,
            average_latency_ms=0.0,
            p50_latency_ms=0.0,
            p95_latency_ms=0.0,
        )

    avg_quality = sum(qualities) / total
    avg_cost = sum(costs) / total
    total_cost = sum(costs)
    avg_strong_cost = sum(strong_baseline_costs) / total if strong_baseline_costs else avg_cost
    avg_strong_quality = sum(strong_baseline_qualities) / total if strong_baseline_qualities else avg_quality

    strong_requests = sum(1 for tier in selected_tiers if tier == "strong")
    routing_accuracy = 1.0
    if optimal_tiers and len(optimal_tiers) == total:
        matches = sum(1 for selected, optimal in zip(selected_tiers, optimal_tiers) if selected == optimal)
        routing_accuracy = matches / total

    return AggregateMetrics(
        total_requests=total,
        average_quality=round(avg_quality, 4),
        average_cost=round(avg_cost, 8),
        total_cost=round(total_cost, 8),
        cost_reduction=cost_reduction(avg_cost, avg_strong_cost),
        quality_retention=quality_retention(avg_quality, avg_strong_quality),
        routing_accuracy=round(routing_accuracy, 4),
        strong_model_usage=strong_model_usage(strong_requests, total),
        average_latency_ms=round(sum(latencies) / total, 2),
        p50_latency_ms=percentile(latencies, 50),
        p95_latency_ms=percentile(latencies, 95),
    )
