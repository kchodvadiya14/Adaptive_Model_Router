"""Background jobs for ML router training.

Thin compatibility wrapper around the generic, SQLite-backed app.services.jobs.JobManager
(Phase 1 Step 4). Public class/function names and behavior are unchanged from before
the migration; only job state persistence changed (previously in-memory, now SQLite).

Note: the original manager set progress to 0.5 (not 0.05) immediately on start, since
training reports no incremental progress while running. Preserved here.
"""

from __future__ import annotations

from typing import Any, Callable, Coroutine

from app.schemas.training import TrainedModelInfo, TrainingJobStatus
from app.services.jobs import JobManager

JOB_TYPE = "training"


class TrainingJobManager:
    def __init__(self) -> None:
        self._manager = JobManager(job_type=JOB_TYPE)

    def create_job(self) -> str:
        return self._manager.create_job()

    def get_job(self, job_id: str) -> TrainingJobStatus | None:
        record = self._manager.get_job(job_id)
        if record is None:
            return None
        return TrainingJobStatus(
            job_id=record.job_id,
            status=record.status,
            progress=record.progress,
            error=record.error,
            result=TrainedModelInfo.model_validate(record.result) if record.result else None,
        )

    def start_job(self, job_id: str, coroutine_factory: Callable[[], Coroutine[Any, Any, Any]]) -> None:
        self._manager.start_job(job_id, coroutine_factory, initial_progress=0.5)


_manager: TrainingJobManager | None = None


def get_training_job_manager() -> TrainingJobManager:
    global _manager
    if _manager is None:
        _manager = TrainingJobManager()
    return _manager
