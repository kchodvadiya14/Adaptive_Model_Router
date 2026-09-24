"""Research experiment runner and final evaluation suite."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from app.evaluation.benchmark import BenchmarkRunner, get_benchmark_runner
from app.router.base import create_router
from app.schemas.evaluation import BenchmarkStrategy
from app.schemas.experiments import (
    ExperimentReport,
    ExperimentRequest,
    ExperimentSection,
    ExperimentType,
    ExperimentVariant,
)


def _variant_from_strategy(strategy_result, *, extra_config: dict[str, Any] | None = None) -> ExperimentVariant:
    config = {"strategy": strategy_result.strategy.value}
    if extra_config:
        config.update(extra_config)
    return ExperimentVariant(
        name=strategy_result.strategy.value,
        description=f"Benchmark strategy: {strategy_result.strategy.value.replace('_', ' ')}",
        metrics=strategy_result.metrics,
        config=config,
    )


def build_experiment_summary(sections: list[ExperimentSection]) -> tuple[str, str]:
    """Build plain-text and markdown summaries from measured experiment variants."""
    if not sections:
        return "No experiment sections completed.", "# Experiment Report\n\nNo sections completed."

    lines = ["Final evaluation completed."]
    md_lines = ["# Final Evaluation Report", "", "Results measured on the configured providers and judge.", ""]

    for section in sections:
        if not section.variants:
            continue
        lines.append(f"{section.name}: {len(section.variants)} variant(s).")
        md_lines.extend([f"## {section.name}", ""])
        md_lines.append("| Variant | Avg Quality | Avg Cost | Cost Reduction | Quality Retention | Strong Usage |")
        md_lines.append("|---------|-------------|----------|----------------|-------------------|--------------|")

        best_cost = min(section.variants, key=lambda item: item.metrics.average_cost)
        best_quality = max(section.variants, key=lambda item: item.metrics.average_quality)

        for variant in section.variants:
            metrics = variant.metrics
            md_lines.append(
                f"| {variant.name} | {metrics.average_quality:.2%} | ${metrics.average_cost:.6f} | "
                f"{metrics.cost_reduction:.2%} | {metrics.quality_retention:.2%} | "
                f"{metrics.strong_model_usage:.2%} |"
            )

        lines.append(
            f"  Lowest cost in '{section.name}': {best_cost.name} "
            f"(${best_cost.metrics.average_cost:.6f}, quality {best_cost.metrics.average_quality:.2%})."
        )
        lines.append(
            f"  Highest quality in '{section.name}': {best_quality.name} "
            f"(quality {best_quality.metrics.average_quality:.2%}, cost ${best_quality.metrics.average_cost:.6f})."
        )
        md_lines.append("")

    return "\n".join(lines), "\n".join(md_lines)


class ExperimentRunner:
    def __init__(self, benchmark_runner: BenchmarkRunner | None = None) -> None:
        self.benchmark_runner = benchmark_runner or get_benchmark_runner()

    async def run(self, request: ExperimentRequest) -> ExperimentReport:
        if request.experiment_type == ExperimentType.STRATEGY_COMPARISON:
            sections = [await self._run_strategy_comparison(request)]
        elif request.experiment_type == ExperimentType.QUALITY_FLOOR_SWEEP:
            sections = [await self._run_quality_floor_sweep(request)]
        elif request.experiment_type == ExperimentType.ROUTER_COMPARISON:
            sections = [await self._run_router_comparison(request)]
        else:
            sections = await self._run_final_evaluation(request)

        summary, markdown_summary = build_experiment_summary(sections)
        return ExperimentReport(
            id=str(uuid.uuid4()),
            name=request.name,
            experiment_type=request.experiment_type.value,
            dataset_path=request.dataset_path,
            created_at=datetime.now(UTC).isoformat(),
            sections=sections,
            summary=summary,
            markdown_summary=markdown_summary,
        )

    async def _run_final_evaluation(self, request: ExperimentRequest) -> list[ExperimentSection]:
        return [
            await self._run_strategy_comparison(request),
            await self._run_quality_floor_sweep(request),
            await self._run_router_comparison(request),
        ]

    async def _run_strategy_comparison(self, request: ExperimentRequest) -> ExperimentSection:
        report = await self.benchmark_runner.run(
            dataset_path=request.dataset_path,
            strategies=request.strategies,
            quality_floor=request.quality_floor,
            max_prompts=request.max_prompts,
        )
        variants = [_variant_from_strategy(item) for item in report.strategies]
        return ExperimentSection(
            name="Strategy Comparison",
            experiment_type=ExperimentType.STRATEGY_COMPARISON.value,
            variants=variants,
        )

    async def _run_quality_floor_sweep(self, request: ExperimentRequest) -> ExperimentSection:
        variants: list[ExperimentVariant] = []
        for quality_floor in request.quality_floors:
            report = await self.benchmark_runner.run(
                dataset_path=request.dataset_path,
                strategies=[BenchmarkStrategy.ADAPTIVE_ROUTER],
                quality_floor=quality_floor,
                max_prompts=request.max_prompts,
            )
            strategy = report.strategies[0]
            variants.append(
                ExperimentVariant(
                    name=f"quality_floor_{quality_floor:.2f}",
                    description=f"Adaptive router with quality floor {quality_floor:.0%}",
                    metrics=strategy.metrics,
                    config={"quality_floor": quality_floor, "router_type": "configured"},
                )
            )
        return ExperimentSection(
            name="Quality Floor Ablation",
            experiment_type=ExperimentType.QUALITY_FLOOR_SWEEP.value,
            variants=variants,
        )

    async def _run_router_comparison(self, request: ExperimentRequest) -> ExperimentSection:
        variants: list[ExperimentVariant] = []
        for router_type in request.router_types:
            try:
                router = create_router(router_type)
            except (FileNotFoundError, ValueError):
                continue

            report = await self.benchmark_runner.run(
                dataset_path=request.dataset_path,
                strategies=[BenchmarkStrategy.ADAPTIVE_ROUTER],
                quality_floor=request.quality_floor,
                max_prompts=request.max_prompts,
                router=router,
            )
            strategy = report.strategies[0]
            variants.append(
                ExperimentVariant(
                    name=router_type,
                    description=f"Adaptive router using {router_type} implementation",
                    metrics=strategy.metrics,
                    config={"router_type": router_type, "quality_floor": request.quality_floor},
                )
            )

        return ExperimentSection(
            name="Router Comparison",
            experiment_type=ExperimentType.ROUTER_COMPARISON.value,
            variants=variants,
        )


_experiment_runner: ExperimentRunner | None = None


def get_experiment_runner() -> ExperimentRunner:
    global _experiment_runner
    if _experiment_runner is None:
        _experiment_runner = ExperimentRunner()
    return _experiment_runner
