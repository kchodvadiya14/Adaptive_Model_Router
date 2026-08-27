"""Pydantic schemas for evaluation and benchmarking."""

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class BenchmarkStrategy(str, Enum):
    ALWAYS_STRONG = "always_strong"
    ALWAYS_CHEAP = "always_cheap"
    ADAPTIVE_ROUTER = "adaptive_router"


class AggregateMetrics(BaseModel):
    total_requests: int
    average_quality: float
    average_cost: float
    total_cost: float
    cost_reduction: float
    quality_retention: float
    routing_accuracy: float
    strong_model_usage: float
    average_latency_ms: float
    p50_latency_ms: float
    p95_latency_ms: float


class JudgeScore(BaseModel):
    correctness: float = Field(ge=0, le=1)
    relevance: float = Field(ge=0, le=1)
    completeness: float = Field(ge=0, le=1)
    reasoning_quality: float = Field(ge=0, le=1)
    instruction_following: float = Field(ge=0, le=1)
    overall: float = Field(ge=0, le=1)
    judge_provider: str
    judge_reasoning: str = ""


class PairwiseJudgeResult(BaseModel):
    winner: str
    confidence: float = Field(ge=0, le=1)
    reason: str
    judge_provider: str


class EvaluateRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=32000)
    response: str = Field(min_length=1, max_length=64000)


class EvaluateResponse(BaseModel):
    scores: JudgeScore


class BenchmarkPrompt(BaseModel):
    id: str
    prompt: str
    category: str | None = None


class BenchmarkRequest(BaseModel):
    dataset_path: str = "data/benchmarks/sample_prompts.json"
    strategies: list[BenchmarkStrategy] = Field(
        default_factory=lambda: [
            BenchmarkStrategy.ALWAYS_STRONG,
            BenchmarkStrategy.ALWAYS_CHEAP,
            BenchmarkStrategy.ADAPTIVE_ROUTER,
        ]
    )
    quality_floor: float = Field(default=0.90, ge=0, le=1)
    max_prompts: int = Field(default=20, ge=1, le=200)


class StrategyResult(BaseModel):
    strategy: BenchmarkStrategy
    metrics: AggregateMetrics
    samples: list[dict[str, Any]] = Field(default_factory=list)


class BenchmarkReport(BaseModel):
    id: str
    dataset_path: str
    quality_floor: float
    created_at: str
    strategies: list[StrategyResult]


class BenchmarkJobStatus(BaseModel):
    job_id: str
    status: Literal["queued", "running", "completed", "failed"]
    progress: float = Field(ge=0, le=1)
    error: str | None = None
    report: BenchmarkReport | None = None


class MetricsSummary(BaseModel):
    total_requests: int
    total_cost: float
    average_cost: float
    average_quality: float | None
    quality_retention: float | None
    cost_saved: float
    average_latency_ms: float
    strong_model_usage: float
    fallback_rate: float = 0.0
    requests_by_model: dict[str, int]
    requests_by_task: dict[str, int]
    requests_by_tier: dict[str, int]
