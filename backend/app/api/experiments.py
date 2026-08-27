"""Research experiment API endpoints."""

from fastapi import APIRouter, BackgroundTasks, HTTPException, status

from app.evaluation.experiment_reports import (
    list_experiment_reports,
    load_experiment_report,
    save_experiment_report,
)
from app.evaluation.experiments import get_experiment_runner
from app.schemas.experiments import ExperimentJobStatus, ExperimentReport, ExperimentRequest
from app.services.experiment_jobs import get_experiment_job_manager

router = APIRouter(prefix="/api/experiments", tags=["experiments"])


async def _execute_experiment_job(job_id: str, request: ExperimentRequest) -> None:
    job_manager = get_experiment_job_manager()
    job_manager.mark_running(job_id)
    try:
        report = await get_experiment_runner().run(request)
        save_experiment_report(report)
        job_manager.mark_completed(job_id, report)
    except Exception as exc:
        job_manager.mark_failed(job_id, str(exc))


@router.post("/run", response_model=ExperimentJobStatus, status_code=status.HTTP_202_ACCEPTED)
async def start_experiment(
    request: ExperimentRequest,
    background_tasks: BackgroundTasks,
) -> ExperimentJobStatus:
    job_manager = get_experiment_job_manager()
    job_id = job_manager.create_job()
    background_tasks.add_task(_execute_experiment_job, job_id, request)
    job = job_manager.get_job(job_id)
    assert job is not None
    return job


@router.get("/status/{job_id}", response_model=ExperimentJobStatus)
def get_experiment_status(job_id: str) -> ExperimentJobStatus:
    job = get_experiment_job_manager().get_job(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Experiment job not found")
    return job


@router.get("", response_model=list[dict])
def list_experiments(limit: int = 20) -> list[dict]:
    return list_experiment_reports(limit=limit)


@router.get("/{report_id}", response_model=ExperimentReport)
def get_experiment(report_id: str) -> ExperimentReport:
    report = load_experiment_report(report_id)
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Experiment report not found")
    return report
