"""Background jobs for research experiments.

Thin compatibility wrapper around the generic, SQLite-backed app.services.jobs.JobManager
(Phase 1 Step 4). Public class/function names and behavior are unchanged from before
the migration; only job state persistence changed (previously in-memory, now SQLite).

Unlike the other job types, experiment jobs are driven manually (mark_running /
mark_completed / mark_failed) by a FastAPI BackgroundTask rather than via start_job();
both call styles are preserved here.
"""

from __future__ import annotations

from typing import Any, Callable, Coroutine

from app.schemas.experiments import ExperimentJobStatus, ExperimentReport
from app.services.jobs import JobManager

JOB_TYPE = "experiment"


class ExperimentJobManager:
    def __init__(self) -> None:
        self._manager = JobManager(job_type=JOB_TYPE)

    def create_job(self) -> str:
        return self._manager.create_job()

    def get_job(self, job_id: str) -> ExperimentJobStatus | None:
        record = self._manager.get_job(job_id)
        if record is None:
            return None
        return ExperimentJobStatus(
            job_id=record.job_id,
            status=record.status,
            progress=record.progress,
            error=record.error,
            report=ExperimentReport.model_validate(record.result) if record.result else None,
        )

    def mark_running(self, job_id: str) -> None:
        self._manager.mark_running(job_id, progress=0.1)

    def mark_completed(self, job_id: str, report: ExperimentReport) -> None:
        self._manager.mark_completed(job_id, report)

    def mark_failed(self, job_id: str, error: str) -> None:
        self._manager.mark_failed(job_id, error)

    def start_job(self, job_id: str, coroutine_factory: Callable[[], Coroutine[Any, Any, Any]]) -> None:
        self._manager.start_job(job_id, coroutine_factory, initial_progress=0.1)


_manager: ExperimentJobManager | None = None


def get_experiment_job_manager() -> ExperimentJobManager:
    global _manager
    if _manager is None:
        _manager = ExperimentJobManager()
    return _manager
