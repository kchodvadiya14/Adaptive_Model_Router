"""Background jobs for dataset generation.

Thin compatibility wrapper around the generic, SQLite-backed app.services.jobs.JobManager
(Phase 1 Step 4). Public class/function names and behavior are unchanged from before
the migration; only job state persistence changed (previously in-memory, now SQLite).
"""

from __future__ import annotations

from typing import Any, Callable, Coroutine

from app.schemas.dataset import DatasetGenerateJobStatus, DatasetManifest
from app.services.jobs import JobManager

JOB_TYPE = "dataset_generate"


class DatasetJobManager:
    def __init__(self) -> None:
        self._manager = JobManager(job_type=JOB_TYPE)

    def create_job(self) -> str:
        return self._manager.create_job()

    def get_job(self, job_id: str) -> DatasetGenerateJobStatus | None:
        record = self._manager.get_job(job_id)
        if record is None:
            return None
        return DatasetGenerateJobStatus(
            job_id=record.job_id,
            status=record.status,
            progress=record.progress,
            error=record.error,
            manifest=DatasetManifest.model_validate(record.result) if record.result else None,
        )

    def start_job(self, job_id: str, coroutine_factory: Callable[[], Coroutine[Any, Any, Any]]) -> None:
        self._manager.start_job(job_id, coroutine_factory, initial_progress=0.05)


_manager: DatasetJobManager | None = None


def get_dataset_job_manager() -> DatasetJobManager:
    global _manager
    if _manager is None:
        _manager = DatasetJobManager()
    return _manager
