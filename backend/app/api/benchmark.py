"""Benchmark API endpoints."""

from fastapi import APIRouter, HTTPException, status

from app.db.repository import get_benchmark_report, list_benchmark_reports, save_benchmark_report
from app.evaluation.benchmark import get_benchmark_runner
from app.evaluation.reports import save_report_file
from app.schemas.evaluation import BenchmarkJobStatus, BenchmarkReport, BenchmarkRequest
from app.services.jobs import get_job_manager

benchmark_router = APIRouter(prefix="/api/benchmark", tags=["benchmark"])
reports_router = APIRouter(prefix="/api/benchmarks", tags=["benchmark"])


@benchmark_router.post("", response_model=BenchmarkJobStatus, status_code=status.HTTP_202_ACCEPTED)
async def start_benchmark(request: BenchmarkRequest) -> BenchmarkJobStatus:
    job_manager = get_job_manager()
    job_id = job_manager.create_job()
    runner = get_benchmark_runner()

    async def _execute() -> BenchmarkReport:
        report = await runner.run(
            dataset_path=request.dataset_path,
            strategies=request.strategies,
            quality_floor=request.quality_floor,
            max_prompts=request.max_prompts,
        )
        save_benchmark_report(report)
        save_report_file(report)
        return report

    job_manager.start_job(job_id, _execute)
    job = job_manager.get_job(job_id)
    assert job is not None
    return job


@benchmark_router.get("/status/{job_id}", response_model=BenchmarkJobStatus)
def get_benchmark_status(job_id: str) -> BenchmarkJobStatus:
    job = get_job_manager().get_job(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Benchmark job not found")
    return job


@reports_router.get("", response_model=list[BenchmarkReport])
def list_benchmarks(limit: int = 20) -> list[BenchmarkReport]:
    return list_benchmark_reports(limit=limit)


@reports_router.get("/{report_id}", response_model=BenchmarkReport)
def get_benchmark(report_id: str) -> BenchmarkReport:
    report = get_benchmark_report(report_id)
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Benchmark report not found")
    return report
