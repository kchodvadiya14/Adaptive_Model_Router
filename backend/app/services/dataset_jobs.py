"""Background jobs for dataset generation."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, Callable, Coroutine

from app.schemas.dataset import DatasetGenerateJobStatus, DatasetManifest


class DatasetJobManager:
    def __init__(self) -> None:
        self.jobs: dict[str, DatasetGenerateJobStatus] = {}

    def create_job(self) -> str:
        job_id = str(uuid.uuid4())
        self.jobs[job_id] = DatasetGenerateJobStatus(job_id=job_id, status="queued", progress=0.0)
        return job_id

    def get_job(self, job_id: str) -> DatasetGenerateJobStatus | None:
        return self.jobs.get(job_id)

    def start_job(self, job_id: str, coroutine_factory: Callable[[], Coroutine[Any, Any, Any]]) -> None:
        if job_id not in self.jobs:
            raise KeyError(job_id)
        self.jobs[job_id] = DatasetGenerateJobStatus(job_id=job_id, status="running", progress=0.05)
        asyncio.create_task(self._run(job_id, coroutine_factory))

    async def _run(self, job_id: str, coroutine_factory: Callable[[], Coroutine[Any, Any, Any]]) -> None:
        try:
            result: DatasetManifest = await coroutine_factory()
            self.jobs[job_id] = DatasetGenerateJobStatus(
                job_id=job_id,
                status="completed",
                progress=1.0,
                manifest=result,
            )
        except Exception as exc:
            self.jobs[job_id] = DatasetGenerateJobStatus(
                job_id=job_id,
                status="failed",
                progress=1.0,
                error=str(exc),
            )


_manager: DatasetJobManager | None = None


def get_dataset_job_manager() -> DatasetJobManager:
    global _manager
    if _manager is None:
        _manager = DatasetJobManager()
    return _manager
