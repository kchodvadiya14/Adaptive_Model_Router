"""Pydantic schemas for research experiments and final evaluation."""

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.evaluation import AggregateMetrics, BenchmarkStrategy


class ExperimentType(str, Enum):
    FINAL_EVALUATION = "final_evaluation"
    STRATEGY_COMPARISON = "strategy_comparison"
    QUALITY_FLOOR_SWEEP = "quality_floor_sweep"
    ROUTER_COMPARISON = "router_comparison"


class ExperimentVariant(BaseModel):
    name: str
    description: str
    metrics: AggregateMetrics
    config: dict[str, Any] = Field(default_factory=dict)


class ExperimentSection(BaseModel):
    name: str
    experiment_type: str
    variants: list[ExperimentVariant] = Field(default_factory=list)


class ExperimentReport(BaseModel):
    id: str
    name: str
    experiment_type: str
    dataset_path: str
    created_at: str
    sections: list[ExperimentSection] = Field(default_factory=list)
    summary: str = ""
    markdown_summary: str = ""


class ExperimentRequest(BaseModel):
    experiment_type: ExperimentType = ExperimentType.FINAL_EVALUATION
    name: str = "Final Evaluation"
    dataset_path: str = "data/benchmarks/sample_prompts.json"
    quality_floor: float = Field(default=0.90, ge=0, le=1)
    max_prompts: int = Field(default=8, ge=1, le=200)
    strategies: list[BenchmarkStrategy] = Field(
        default_factory=lambda: [
            BenchmarkStrategy.ALWAYS_STRONG,
            BenchmarkStrategy.ALWAYS_CHEAP,
            BenchmarkStrategy.ADAPTIVE_ROUTER,
        ]
    )
    quality_floors: list[float] = Field(default_factory=lambda: [0.85, 0.90, 0.95])
    router_types: list[str] = Field(default_factory=lambda: ["rule_based", "tfidf", "embedding", "bert"])


class ExperimentJobStatus(BaseModel):
    job_id: str
    status: Literal["queued", "running", "completed", "failed"]
    progress: float = Field(ge=0, le=1)
    error: str | None = None
    report: ExperimentReport | None = None
