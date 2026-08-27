"""Tests for benchmark runner and API."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.registry import ModelRegistry

client = TestClient(app)


@pytest.fixture
def temp_registry(tmp_path, monkeypatch):
    registry_path = tmp_path / "model_registry.json"
    registry = ModelRegistry(registry_path=registry_path)
    monkeypatch.setattr("app.models.registry._registry", registry)
    monkeypatch.setattr("app.evaluation.benchmark.get_model_registry", lambda: registry)
    monkeypatch.setattr("app.router.rule_based.get_model_registry", lambda: registry)
    monkeypatch.setattr("app.router.policy.get_model_registry", lambda: registry)
    monkeypatch.setattr("app.services.chat.get_model_registry", lambda: registry)
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


@pytest.mark.asyncio
async def test_benchmark_runner(temp_registry, sample_dataset):
    from app.evaluation.benchmark import BenchmarkRunner
    from app.schemas.evaluation import BenchmarkStrategy

    runner = BenchmarkRunner()
    report = await runner.run(
        dataset_path=sample_dataset,
        strategies=[BenchmarkStrategy.ALWAYS_CHEAP, BenchmarkStrategy.ADAPTIVE_ROUTER],
        quality_floor=0.85,
        max_prompts=2,
    )
    assert len(report.strategies) == 2
    for strategy in report.strategies:
        assert strategy.metrics.total_requests == 2
        assert strategy.metrics.average_quality >= 0


def test_evaluate_endpoint():
    response = client.post(
        "/api/evaluate",
        json={
            "prompt": "Explain gravity.",
            "response": "Gravity is the force that attracts objects with mass toward each other.",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "scores" in data
    assert 0 <= data["scores"]["overall"] <= 1


def test_metrics_endpoint_after_chat(temp_registry, tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    from app.config.settings import get_settings

    get_settings.cache_clear()
    from app.db import database

    database.init_db()

    chat_response = client.post(
        "/api/chat",
        json={"model": "mock-echo", "messages": [{"role": "user", "content": "Hello"}]},
    )
    assert chat_response.status_code == 200

    metrics = client.get("/api/metrics")
    assert metrics.status_code == 200
    assert metrics.json()["total_requests"] >= 1

    get_settings.cache_clear()
