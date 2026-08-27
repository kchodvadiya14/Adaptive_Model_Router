"""Background jobs for ML router training."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, Callable, Coroutine

from app.schemas.training import TrainingJobStatus, TrainedModelInfo


class TrainingJobManager:
    def __init__(self) -> None:
        self.jobs: dict[str, TrainingJobStatus] = {}

    def create_job(self) -> str:
        job_id = str(uuid.uuid4())
        self.jobs[job_id] = TrainingJobStatus(job_id=job_id, status="queued", progress=0.0)
        return job_id

    def get_job(self, job_id: str) -> TrainingJobStatus | None:
        return self.jobs.get(job_id)

    def start_job(self, job_id: str, coroutine_factory: Callable[[], Coroutine[Any, Any, Any]]) -> None:
        if job_id not in self.jobs:
            raise KeyError(job_id)
        self.jobs[job_id] = TrainingJobStatus(job_id=job_id, status="running", progress=0.5)
        asyncio.create_task(self._run(job_id, coroutine_factory))

    async def _run(self, job_id: str, coroutine_factory: Callable[[], Coroutine[Any, Any, Any]]) -> None:
        try:
            result: TrainedModelInfo = await coroutine_factory()
            self.jobs[job_id] = TrainingJobStatus(
                job_id=job_id,
                status="completed",
                progress=1.0,
                result=result,
            )
        except Exception as exc:
            self.jobs[job_id] = TrainingJobStatus(
                job_id=job_id,
                status="failed",
                progress=1.0,
                error=str(exc),
            )


_manager: TrainingJobManager | None = None


def get_training_job_manager() -> TrainingJobManager:
    global _manager
    if _manager is None:
        _manager = TrainingJobManager()
    return _manager
