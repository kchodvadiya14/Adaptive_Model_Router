"""Tests for research experiment runner and API."""

import pytest
from fastapi.testclient import TestClient

from app.evaluation.experiments import ExperimentRunner, build_experiment_summary
from app.main import app
from app.models.registry import ModelRegistry
from app.schemas.experiments import ExperimentRequest, ExperimentSection, ExperimentType, ExperimentVariant
from app.schemas.evaluation import AggregateMetrics

client = TestClient(app)


@pytest.fixture
def temp_registry(tmp_path, monkeypatch):
    registry_path = tmp_path / "model_registry.json"
    registry = ModelRegistry(registry_path=registry_path)
    monkeypatch.setattr("app.models.registry._registry", registry)
    monkeypatch.setattr("app.evaluation.benchmark.get_model_registry", lambda: registry)
    monkeypatch.setattr("app.router.rule_based.get_model_registry", lambda: registry)
    monkeypatch.setattr("app.router.policy.get_model_registry", lambda: registry)
    return registry


@pytest.fixture
def sample_dataset(tmp_path):
    dataset_path = tmp_path / "prompts.json"
    dataset_path.write_text(
        '[{"id":"1","prompt":"What is Python?","category":"general_qa"},'
        '{"id":"2","prompt":"Summarize the water cycle.","category":"summarization"}]',
        encoding="utf-8",
    )
    return str(dataset_path)


@pytest.fixture
def experiment_reports_dir(tmp_path, monkeypatch):
    reports_dir = tmp_path / "reports"
    monkeypatch.setattr("app.evaluation.experiment_reports.REPORTS_DIR", reports_dir)
    monkeypatch.setattr("app.evaluation.experiment_reports.INDEX_PATH", reports_dir / "index.json")
    return reports_dir


@pytest.mark.asyncio
async def test_strategy_comparison_experiment(temp_registry, sample_dataset):
    runner = ExperimentRunner()
    report = await runner.run(
        ExperimentRequest(
            experiment_type=ExperimentType.STRATEGY_COMPARISON,
            dataset_path=sample_dataset,
            max_prompts=2,
            quality_floor=0.85,
        )
    )
    assert report.experiment_type == "strategy_comparison"
    assert len(report.sections) == 1
    assert len(report.sections[0].variants) == 3
    assert report.summary


@pytest.mark.asyncio
async def test_quality_floor_sweep_experiment(temp_registry, sample_dataset):
    runner = ExperimentRunner()
    report = await runner.run(
        ExperimentRequest(
            experiment_type=ExperimentType.QUALITY_FLOOR_SWEEP,
            dataset_path=sample_dataset,
            max_prompts=2,
            quality_floors=[0.85, 0.9],
        )
    )
    assert len(report.sections) == 1
    assert len(report.sections[0].variants) == 2


@pytest.mark.asyncio
async def test_final_evaluation_runs_all_sections(temp_registry, sample_dataset):
    runner = ExperimentRunner()
    report = await runner.run(
        ExperimentRequest(
            experiment_type=ExperimentType.FINAL_EVALUATION,
            dataset_path=sample_dataset,
            max_prompts=2,
            quality_floors=[0.85, 0.9],
            router_types=["rule_based"],
        )
    )
    assert len(report.sections) == 3
    assert report.markdown_summary.startswith("# Final Evaluation Report")


def test_build_experiment_summary_from_metrics():
    section = ExperimentSection(
        name="Strategy Comparison",
        experiment_type="strategy_comparison",
        variants=[
            ExperimentVariant(
                name="always_cheap",
                description="cheap",
                metrics=AggregateMetrics(
                    total_requests=2,
                    average_quality=0.8,
                    average_cost=0.001,
                    total_cost=0.002,
                    cost_reduction=0.5,
                    quality_retention=0.9,
                    routing_accuracy=1.0,
                    strong_model_usage=0.0,
                    average_latency_ms=50,
                    p50_latency_ms=50,
                    p95_latency_ms=55,
                ),
            ),
            ExperimentVariant(
                name="always_strong",
                description="strong",
                metrics=AggregateMetrics(
                    total_requests=2,
                    average_quality=0.95,
                    average_cost=0.01,
                    total_cost=0.02,
                    cost_reduction=0.0,
                    quality_retention=1.0,
                    routing_accuracy=1.0,
                    strong_model_usage=1.0,
                    average_latency_ms=100,
                    p50_latency_ms=100,
                    p95_latency_ms=110,
                ),
            ),
        ],
    )
    summary, markdown = build_experiment_summary([section])
    assert "always_cheap" in summary
    assert "always_strong" in summary
    assert "| always_cheap |" in markdown


@pytest.fixture
def experiment_job_manager(monkeypatch):
    from app.services import experiment_jobs

    manager = experiment_jobs.ExperimentJobManager()
    monkeypatch.setattr(experiment_jobs, "_manager", manager)
    return manager


def test_experiment_api_start_and_poll(
    temp_registry, sample_dataset, experiment_reports_dir, experiment_job_manager
):
    response = client.post(
        "/api/experiments/run",
        json={
            "experiment_type": "strategy_comparison",
            "dataset_path": sample_dataset,
            "max_prompts": 2,
            "strategies": ["always_cheap", "adaptive_router"],
        },
    )
    assert response.status_code == 202
    job_id = response.json()["job_id"]

    import time

    for _ in range(30):
        status_response = client.get(f"/api/experiments/status/{job_id}")
        assert status_response.status_code == 200
        status = status_response.json()
        if status["status"] == "completed":
            assert status["report"] is not None
            assert status["report"]["sections"]
            break
        if status["status"] == "failed":
            pytest.fail(status.get("error"))
        time.sleep(0.2)
    else:
        pytest.fail("Experiment did not complete in time")
