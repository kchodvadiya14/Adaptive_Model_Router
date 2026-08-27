"""Background jobs for research experiments."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, Callable, Coroutine

from app.schemas.experiments import ExperimentJobStatus, ExperimentReport


class ExperimentJobManager:
    def __init__(self) -> None:
        self.jobs: dict[str, ExperimentJobStatus] = {}

    def create_job(self) -> str:
        job_id = str(uuid.uuid4())
        self.jobs[job_id] = ExperimentJobStatus(job_id=job_id, status="queued", progress=0.0)
        return job_id

    def get_job(self, job_id: str) -> ExperimentJobStatus | None:
        return self.jobs.get(job_id)

    def mark_running(self, job_id: str) -> None:
        if job_id not in self.jobs:
            raise KeyError(job_id)
        self.jobs[job_id] = ExperimentJobStatus(job_id=job_id, status="running", progress=0.1)

    def mark_completed(self, job_id: str, report: ExperimentReport) -> None:
        if job_id not in self.jobs:
            raise KeyError(job_id)
        self.jobs[job_id] = ExperimentJobStatus(
            job_id=job_id,
            status="completed",
            progress=1.0,
            report=report,
        )

    def mark_failed(self, job_id: str, error: str) -> None:
        if job_id not in self.jobs:
            raise KeyError(job_id)
        self.jobs[job_id] = ExperimentJobStatus(
            job_id=job_id,
            status="failed",
            progress=1.0,
            error=error,
        )

    def start_job(self, job_id: str, coroutine_factory: Callable[[], Coroutine[Any, Any, Any]]) -> None:
        if job_id not in self.jobs:
            raise KeyError(job_id)
        self.jobs[job_id] = ExperimentJobStatus(job_id=job_id, status="running", progress=0.1)
        asyncio.create_task(self._run(job_id, coroutine_factory))

    async def _run(self, job_id: str, coroutine_factory: Callable[[], Coroutine[Any, Any, Any]]) -> None:
        try:
            result: ExperimentReport = await coroutine_factory()
            self.jobs[job_id] = ExperimentJobStatus(
                job_id=job_id,
                status="completed",
                progress=1.0,
                report=result,
            )
        except Exception as exc:
            self.jobs[job_id] = ExperimentJobStatus(
                job_id=job_id,
                status="failed",
                progress=1.0,
                error=str(exc),
            )


_manager: ExperimentJobManager | None = None


def get_experiment_job_manager() -> ExperimentJobManager:
    global _manager
    if _manager is None:
        _manager = ExperimentJobManager()
    return _manager
