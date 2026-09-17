"""Generic, SQLite-backed background job manager.

Replaces the four previously-duplicated in-memory job managers (benchmark, dataset,
training, experiments). Job STATE (status/progress/error/result) is persisted, so it
survives a backend restart; the coroutine that does the work is still run in-process
via asyncio.create_task — no external queue (Celery/RQ/Redis) is introduced here.

Domain-specific compatibility wrappers (BenchmarkJobManager here, plus
DatasetJobManager / TrainingJobManager / ExperimentJobManager in their own modules)
sit on top of this and are what API routes actually import — their public methods
and the Pydantic *JobStatus schemas they return are unchanged.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Coroutine

from pydantic import BaseModel

from app.db import job_repository
from app.schemas.evaluation import BenchmarkJobStatus, BenchmarkReport

logger = logging.getLogger(__name__)

INTERRUPTED_MESSAGE = "Job interrupted: the backend restarted before this job finished."


@dataclass
class JobRecord:
    """A generic, job-type-agnostic view of a persisted job row."""

    job_id: str
    job_type: str
    status: str
    progress: float
    error: str | None
    result: dict[str, Any] | None
    created_at: str
    started_at: str | None
    completed_at: str | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "JobRecord":
        result_json = row.get("result_json")
        return cls(
            job_id=row["job_id"],
            job_type=row["job_type"],
            status=row["status"],
            progress=row["progress"],
            error=row.get("error"),
            result=json.loads(result_json) if result_json else None,
            created_at=row["created_at"],
            started_at=row.get("started_at"),
            completed_at=row.get("completed_at"),
        )


def _serialize_result(result: BaseModel | dict[str, Any] | None) -> str | None:
    """Only structured payloads (a Pydantic model or a plain dict) are ever persisted —
    never an arbitrary Python object."""
    if result is None:
        return None
    if isinstance(result, BaseModel):
        return result.model_dump_json()
    if isinstance(result, dict):
        return json.dumps(result)
    raise TypeError(f"Job result must be a Pydantic model or dict, got {type(result)!r}")


class JobManager:
    """Generic background job manager for one job type.

    Usage mirrors the original in-memory managers: create_job() -> job_id,
    start_job(job_id, coroutine_factory) to run work in the background, get_job(job_id)
    to poll. mark_running/mark_completed/mark_failed are also exposed for callers (like
    the experiments API) that drive job state manually instead of via start_job.
    """

    def __init__(self, job_type: str) -> None:
        self.job_type = job_type
        # Anything left "queued"/"running" for this job_type predates this process —
        # the in-process task that would finish it is gone. Sweep once at construction
        # time (i.e. on startup, since callers hold one long-lived instance per type).
        interrupted = job_repository.mark_stale_jobs_failed(job_type, INTERRUPTED_MESSAGE)
        if interrupted:
            logger.warning(
                "Marked %d stale '%s' job(s) as failed after restart", interrupted, job_type
            )

    def create_job(self) -> str:
        job_id = str(uuid.uuid4())
        job_repository.create_job(job_id, self.job_type)
        return job_id

    def get_job(self, job_id: str) -> JobRecord | None:
        row = job_repository.get_job(job_id, job_type=self.job_type)
        return JobRecord.from_row(row) if row else None

    def _require_exists(self, job_id: str) -> None:
        if job_repository.get_job(job_id, job_type=self.job_type) is None:
            raise KeyError(job_id)

    def mark_running(self, job_id: str, progress: float = 0.05) -> None:
        self._require_exists(job_id)
        job_repository.update_job(job_id, status="running", progress=progress, set_started_now=True)

    def update_progress(self, job_id: str, progress: float) -> None:
        self._require_exists(job_id)
        job_repository.update_job(job_id, progress=progress)

    def mark_completed(self, job_id: str, result: BaseModel | dict[str, Any] | None = None) -> None:
        self._require_exists(job_id)
        job_repository.update_job(
            job_id,
            status="completed",
            progress=1.0,
            clear_error=True,
            result_json=_serialize_result(result) if result is not None else None,
            set_completed_now=True,
        )

    def mark_failed(self, job_id: str, error: str) -> None:
        self._require_exists(job_id)
        job_repository.update_job(job_id, status="failed", progress=1.0, error=error, set_completed_now=True)

    def start_job(
        self,
        job_id: str,
        coroutine_factory: Callable[[], Coroutine[Any, Any, Any]],
        *,
        initial_progress: float = 0.05,
    ) -> None:
        self._require_exists(job_id)
        self.mark_running(job_id, progress=initial_progress)
        asyncio.create_task(self._run(job_id, coroutine_factory))

    async def _run(
        self,
        job_id: str,
        coroutine_factory: Callable[[], Coroutine[Any, Any, Any]],
    ) -> None:
        try:
            result = await coroutine_factory()
            self.mark_completed(job_id, result)
        except Exception as exc:
            logger.exception("Job %s (%s) failed", job_id, self.job_type)
            self.mark_failed(job_id, str(exc))


# --- Benchmark job compatibility wrapper (previously this module's own JobManager) -----


class BenchmarkJobManager:
    """Preserves the original benchmark job manager's public contract, backed by the
    generic, persistent JobManager above."""

    def __init__(self) -> None:
        self._manager = JobManager(job_type="benchmark")

    def create_job(self) -> str:
        return self._manager.create_job()

    def get_job(self, job_id: str) -> BenchmarkJobStatus | None:
        record = self._manager.get_job(job_id)
        if record is None:
            return None
        return BenchmarkJobStatus(
            job_id=record.job_id,
            status=record.status,
            progress=record.progress,
            error=record.error,
            report=BenchmarkReport.model_validate(record.result) if record.result else None,
        )

    def start_job(
        self,
        job_id: str,
        coroutine_factory: Callable[[], Coroutine[Any, Any, Any]],
    ) -> None:
        self._manager.start_job(job_id, coroutine_factory, initial_progress=0.05)


_job_manager: BenchmarkJobManager | None = None


def get_job_manager() -> BenchmarkJobManager:
    global _job_manager
    if _job_manager is None:
        _job_manager = BenchmarkJobManager()
    return _job_manager
