"""Pydantic schemas for preference dataset pipeline."""

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.evaluation import JudgeScore


class PreferenceRecord(BaseModel):
    id: str
    prompt: str
    task_type: str
    difficulty: float = Field(ge=0, le=1)

    small_model_id: str
    medium_model_id: str
    strong_model_id: str

    small_response: str
    medium_response: str
    strong_response: str

    small_score: float = Field(ge=0, le=1)
    medium_score: float = Field(ge=0, le=1)
    strong_score: float = Field(ge=0, le=1)

    small_judge: JudgeScore | None = None
    medium_judge: JudgeScore | None = None
    strong_judge: JudgeScore | None = None

    preferred_model: Literal["small", "medium", "strong"]
    small_sufficient: bool
    medium_sufficient: bool
    strong_sufficient: bool

    quality_floor: float = Field(ge=0, le=1)
    evaluation_source: Literal["judge", "human", "mixed"] = "judge"
    human_notes: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DatasetManifest(BaseModel):
    id: str
    name: str
    created_at: str
    source_path: str
    output_path: str
    quality_floor: float
    record_count: int
    judge_provider: str
    description: str = ""


class DatasetGenerateRequest(BaseModel):
    source_path: str = "data/benchmarks/sample_prompts.json"
    name: str = "preference_dataset"
    quality_floor: float = Field(default=0.90, ge=0, le=1)
    max_prompts: int = Field(default=20, ge=1, le=500)
    description: str = ""


class DatasetGenerateJobStatus(BaseModel):
    job_id: str
    status: Literal["queued", "running", "completed", "failed"]
    progress: float = Field(ge=0, le=1)
    error: str | None = None
    manifest: DatasetManifest | None = None


class HumanEvaluationRequest(BaseModel):
    record_id: str
    small_score: float | None = Field(default=None, ge=0, le=1)
    medium_score: float | None = Field(default=None, ge=0, le=1)
    strong_score: float | None = Field(default=None, ge=0, le=1)
    preferred_model: Literal["small", "medium", "strong"] | None = None
    notes: str | None = None


class DatasetRecordsResponse(BaseModel):
    manifest: DatasetManifest
    records: list[PreferenceRecord]
    total: int
    offset: int
    limit: int
