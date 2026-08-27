"""Pydantic schemas for ML router training."""

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class RouterTrainType(str, Enum):
    TFIDF = "tfidf"
    EMBEDDING = "embedding"
    BERT = "bert"


class ConfusionMatrix(BaseModel):
    true_negative: int
    false_positive: int
    false_negative: int
    true_positive: int


class TrainingMetrics(BaseModel):
    train_accuracy: float
    validation_accuracy: float
    test_accuracy: float
    precision: float
    recall: float
    f1: float
    routing_threshold: float
    confusion_matrix: ConfusionMatrix
    probability_mean: float | None = None


class TrainedModelInfo(BaseModel):
    id: str
    router_type: RouterTrainType
    dataset_id: str
    model_path: str
    created_at: str
    metrics: TrainingMetrics
    threshold: float
    samples: int


class TrainingStartRequest(BaseModel):
    dataset_id: str
    router_type: RouterTrainType
    routing_threshold: float | None = Field(default=None, ge=0.0, le=1.0)


class TrainingJobStatus(BaseModel):
    job_id: str
    status: Literal["queued", "running", "completed", "failed"]
    progress: float = Field(ge=0, le=1)
    error: str | None = None
    result: TrainedModelInfo | None = None
