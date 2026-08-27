"""Training API endpoints."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, status

from app.schemas.training import RouterTrainType, TrainingJobStatus, TrainingStartRequest, TrainedModelInfo
from app.services.training_jobs import get_training_job_manager
from app.training.registry import load_registry
from app.training.service import get_training_service

router = APIRouter(prefix="/api/training", tags=["training"])


@router.post("/start", response_model=TrainingJobStatus, status_code=status.HTTP_202_ACCEPTED)
async def start_training(request: TrainingStartRequest) -> TrainingJobStatus:
    job_manager = get_training_job_manager()
    job_id = job_manager.create_job()
    service = get_training_service()

    async def _execute() -> TrainedModelInfo:
        return await asyncio.to_thread(
            service.train,
            request.dataset_id,
            request.router_type,
            request.routing_threshold,
        )

    job_manager.start_job(job_id, _execute)
    job = job_manager.get_job(job_id)
    assert job is not None
    return job


@router.get("/status/{job_id}", response_model=TrainingJobStatus)
def training_status(job_id: str) -> TrainingJobStatus:
    job = get_training_job_manager().get_job(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Training job not found")
    return job


@router.get("/models", response_model=list[TrainedModelInfo])
def list_trained_models() -> list[TrainedModelInfo]:
    return load_registry()
