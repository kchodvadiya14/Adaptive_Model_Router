"""Benchmark runner comparing routing strategies."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.datasets.json_dataset import JsonDatasetAdapter
from app.evaluation.judge import get_judge
from app.evaluation.metrics import compute_aggregate_metrics
from app.models.registry import get_model_registry
from app.providers.base import GenerationRequest
from app.providers.factory import get_provider_for_model
from app.router.base import get_router
from app.router.policy import estimate_prompt_cost
from app.schemas.evaluation import BenchmarkPrompt, BenchmarkReport, BenchmarkStrategy, StrategyResult
from app.schemas.models import ModelTier
from app.schemas.routing import RouteRequest


class BenchmarkRunner:
    async def run(
        self,
        dataset_path: str,
        strategies: list[BenchmarkStrategy],
        quality_floor: float,
        max_prompts: int,
        router=None,
    ) -> BenchmarkReport:
        adapter = JsonDatasetAdapter(dataset_path)
        prompts = adapter.load()[:max_prompts]
        registry = get_model_registry()
        judge = get_judge()
        router = router or get_router()

        strong_model = registry.get_primary_model_for_tier(ModelTier.STRONG)
        cheap_model = registry.get_primary_model_for_tier(ModelTier.SMALL)
        if not strong_model or not cheap_model:
            raise ValueError("Strong and small tier models must be enabled for benchmarking.")

        strategy_results: list[StrategyResult] = []

        for strategy in strategies:
            qualities: list[float] = []
            costs: list[float] = []
            latencies: list[float] = []
            strong_costs: list[float] = []
            strong_qualities: list[float] = []
            tiers: list[str] = []
            samples: list[dict] = []

            for item in prompts:
                sample = await self._evaluate_prompt(
                    item=item,
                    strategy=strategy,
                    quality_floor=quality_floor,
                    router=router,
                    judge=judge,
                    strong_model_id=strong_model.id,
                    cheap_model_id=cheap_model.id,
                )
                qualities.append(sample["quality"])
                costs.append(sample["cost"])
                latencies.append(sample["latency_ms"])
                strong_costs.append(sample["strong_baseline_cost"])
                strong_qualities.append(sample["strong_baseline_quality"])
                tiers.append(sample["tier"])
                samples.append(sample)

            metrics = compute_aggregate_metrics(
                qualities=qualities,
                costs=costs,
                latencies=latencies,
                strong_baseline_costs=strong_costs,
                strong_baseline_qualities=strong_qualities,
                selected_tiers=tiers,
            )
            strategy_results.append(StrategyResult(strategy=strategy, metrics=metrics, samples=samples))

        report = BenchmarkReport(
            id=str(uuid.uuid4()),
            dataset_path=dataset_path,
            quality_floor=quality_floor,
            created_at=datetime.now(UTC).isoformat(),
            strategies=strategy_results,
        )
        return report

    async def _evaluate_prompt(
        self,
        *,
        item: BenchmarkPrompt,
        strategy: BenchmarkStrategy,
        quality_floor: float,
        router,
        judge,
        strong_model_id: str,
        cheap_model_id: str,
    ) -> dict:
        registry = get_model_registry()
        strong_model = registry.get_model(strong_model_id)
        cheap_model = registry.get_model(cheap_model_id)
        assert strong_model and cheap_model

        if strategy == BenchmarkStrategy.ALWAYS_STRONG:
            selected_model_id = strong_model.id
            routing_meta = None
        elif strategy == BenchmarkStrategy.ALWAYS_CHEAP:
            selected_model_id = cheap_model.id
            routing_meta = None
        else:
            routing_meta = router.route(
                RouteRequest(prompt=item.prompt),
                configuration={"quality_floor": quality_floor},
            )
            selected_model_id = routing_meta.selected_model

        selected_model = registry.get_model(selected_model_id)
        if not selected_model:
            raise ValueError(f"Selected model not found: {selected_model_id}")

        provider = get_provider_for_model(selected_model)
        generation = await provider.generate(
            GenerationRequest(messages=[{"role": "user", "content": item.prompt}], max_tokens=512)
        )
        score = await judge.evaluate(item.prompt, generation.content)

        strong_provider = get_provider_for_model(strong_model)
        strong_generation = await strong_provider.generate(
            GenerationRequest(messages=[{"role": "user", "content": item.prompt}], max_tokens=512)
        )
        strong_score = await judge.evaluate(item.prompt, strong_generation.content)

        actual_cost = provider.estimate_cost(generation.input_tokens, generation.output_tokens).total_cost
        strong_baseline_cost = estimate_prompt_cost(strong_model, item.prompt, expected_output_tokens=generation.output_tokens)

        return {
            "prompt_id": item.id,
            "prompt": item.prompt,
            "strategy": strategy.value,
            "selected_model": selected_model.id,
            "tier": selected_model.tier.value,
            "quality": score.overall,
            "cost": actual_cost,
            "latency_ms": generation.latency_ms,
            "strong_baseline_cost": strong_baseline_cost,
            "strong_baseline_quality": strong_score.overall,
            "judge_reasoning": score.judge_reasoning,
            "routing": routing_meta.model_dump() if routing_meta else None,
        }


_benchmark_runner: BenchmarkRunner | None = None


def get_benchmark_runner() -> BenchmarkRunner:
    global _benchmark_runner
    if _benchmark_runner is None:
        _benchmark_runner = BenchmarkRunner()
    return _benchmark_runner
