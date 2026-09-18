"""Preference dataset API endpoints."""

from fastapi import APIRouter, HTTPException, status

from app.datasets.generator import compute_preference_labels, get_dataset_generator
from app.datasets.storage import get_manifest, load_index, load_records, update_record
from app.schemas.dataset import (
    DatasetGenerateJobStatus,
    DatasetGenerateRequest,
    DatasetManifest,
    DatasetRecordsResponse,
    HumanEvaluationRequest,
    PreferenceRecord,
)
from app.services.dataset_jobs import get_dataset_job_manager

router = APIRouter(prefix="/api/dataset", tags=["dataset"])


@router.post("/generate", response_model=DatasetGenerateJobStatus, status_code=status.HTTP_202_ACCEPTED)
async def generate_dataset(request: DatasetGenerateRequest) -> DatasetGenerateJobStatus:
    job_manager = get_dataset_job_manager()
    job_id = job_manager.create_job()
    generator = get_dataset_generator()

    async def _execute():
        return await generator.generate(
            source_path=request.source_path,
            name=request.name,
            quality_floor=request.quality_floor,
            max_prompts=request.max_prompts,
            description=request.description,
            on_progress=lambda fraction: job_manager.update_progress(job_id, 0.05 + 0.9 * fraction),
        )

    job_manager.start_job(job_id, _execute)
    job = job_manager.get_job(job_id)
    assert job is not None
    return job


@router.get("/generate/status/{job_id}", response_model=DatasetGenerateJobStatus)
def get_generation_status(job_id: str) -> DatasetGenerateJobStatus:
    job = get_dataset_job_manager().get_job(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset job not found")
    return job


@router.get("", response_model=list[DatasetManifest])
def list_datasets() -> list[DatasetManifest]:
    return load_index()


@router.get("/{dataset_id}", response_model=DatasetRecordsResponse)
def get_dataset(dataset_id: str, offset: int = 0, limit: int = 50) -> DatasetRecordsResponse:
    manifest = get_manifest(dataset_id)
    if not manifest:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found")
    records = load_records(dataset_id)
    page = records[offset : offset + limit]
    return DatasetRecordsResponse(
        manifest=manifest,
        records=page,
        total=len(records),
        offset=offset,
        limit=limit,
    )


@router.post("/{dataset_id}/human-eval", response_model=PreferenceRecord)
def submit_human_evaluation(dataset_id: str, request: HumanEvaluationRequest) -> PreferenceRecord:
    manifest = get_manifest(dataset_id)
    if not manifest:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found")

    records = load_records(dataset_id)
    record = next((item for item in records if item.id == request.record_id), None)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Record not found")

    small_score = request.small_score if request.small_score is not None else record.small_score
    medium_score = request.medium_score if request.medium_score is not None else record.medium_score
    strong_score = request.strong_score if request.strong_score is not None else record.strong_score

    preferred, small_ok, medium_ok, strong_ok = compute_preference_labels(
        small_score, medium_score, strong_score, record.quality_floor
    )
    if request.preferred_model:
        preferred = request.preferred_model

    updated = record.model_copy(
        update={
            "small_score": small_score,
            "medium_score": medium_score,
            "strong_score": strong_score,
            "preferred_model": preferred,
            "small_sufficient": small_ok,
            "medium_sufficient": medium_ok,
            "strong_sufficient": strong_ok,
            "evaluation_source": "human" if request.preferred_model else "mixed",
            "human_notes": request.notes,
        }
    )
    update_record(dataset_id, updated)
    return updated
