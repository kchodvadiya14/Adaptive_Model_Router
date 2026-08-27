"""Tests for ML router training and inference."""

import pytest

from app.models.registry import ModelRegistry
from app.router.tfidf_router import TFIDFRouter
from app.schemas.routing import RouteRequest
from app.schemas.training import RouterTrainType
from app.training.registry import load_latest_artifact
from app.training.train_tfidf import train_tfidf_router


@pytest.fixture
def temp_registry(tmp_path, monkeypatch):
    registry_path = tmp_path / "model_registry.json"
    registry = ModelRegistry(registry_path=registry_path)
    monkeypatch.setattr("app.models.registry._registry", registry)
    monkeypatch.setattr("app.datasets.generator.get_model_registry", lambda: registry)
    monkeypatch.setattr("app.router.rule_based.get_model_registry", lambda: registry)
    monkeypatch.setattr("app.router.policy.get_model_registry", lambda: registry)
    monkeypatch.setattr("app.router.ml_base.get_model_registry", lambda: registry)
    return registry


@pytest.fixture
def temp_storage(tmp_path, monkeypatch):
    datasets_dir = tmp_path / "datasets"
    datasets_dir.mkdir()
    monkeypatch.setattr("app.datasets.storage.DATASETS_DIR", datasets_dir)
    monkeypatch.setattr("app.datasets.storage.INDEX_PATH", datasets_dir / "index.json")
    monkeypatch.setattr(
        "app.datasets.storage.dataset_path",
        lambda dataset_id: datasets_dir / f"{dataset_id}.jsonl",
    )
    return datasets_dir


@pytest.fixture
def temp_models(tmp_path, monkeypatch):
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    monkeypatch.setattr("app.training.registry.MODELS_DIR", models_dir)
    monkeypatch.setattr("app.training.registry.REGISTRY_PATH", models_dir / "registry.json")
    monkeypatch.setattr(
        "app.training.registry.artifact_path",
        lambda model_id, router_type: models_dir / f"{router_type.value}_{model_id}.joblib",
    )
    return models_dir


@pytest.fixture
def sample_dataset(temp_registry, temp_storage):
    from datetime import UTC, datetime
    import uuid

    from app.datasets.storage import add_manifest, save_records
    from app.schemas.dataset import DatasetManifest, PreferenceRecord

    dataset_id = str(uuid.uuid4())
    records: list[PreferenceRecord] = []
    for i in range(8):
        strong_wins = i % 2 == 0
        records.append(
            PreferenceRecord(
                id=f"r{i}",
                prompt=f"Explain concept {i} with examples and reasoning.",
                task_type="general_qa",
                difficulty=0.4 if not strong_wins else 0.8,
                small_model_id="mock-echo",
                medium_model_id="mock-echo-medium",
                strong_model_id="mock-echo-strong",
                small_response="short",
                medium_response="medium",
                strong_response="long detailed",
                small_score=0.72,
                medium_score=0.84,
                strong_score=0.94 if strong_wins else 0.78,
                preferred_model="strong" if strong_wins else "small",
                small_sufficient=not strong_wins,
                medium_sufficient=True,
                strong_sufficient=True,
                quality_floor=0.85,
            )
        )
    save_records(dataset_id, records)
    manifest = DatasetManifest(
        id=dataset_id,
        name="ml_test",
        created_at=datetime.now(UTC).isoformat(),
        source_path="test",
        output_path=str(dataset_id),
        quality_floor=0.85,
        record_count=len(records),
        judge_provider="mock",
    )
    add_manifest(manifest)
    return manifest


def test_train_tfidf_router(sample_dataset, temp_models):
    info = train_tfidf_router(sample_dataset.id, routing_threshold=0.6)
    assert info.router_type == RouterTrainType.TFIDF
    assert info.metrics.test_accuracy >= 0.0
    assert load_latest_artifact(RouterTrainType.TFIDF) is not None


def test_tfidf_router_route(sample_dataset, temp_models, monkeypatch):
    train_tfidf_router(sample_dataset.id, routing_threshold=0.6)
    monkeypatch.setenv("ROUTER_TYPE", "tfidf")
    from app.config.settings import get_settings

    get_settings.cache_clear()
    router = TFIDFRouter()
    decision = router.route(RouteRequest(prompt="Explain recursion in Python with examples."))
    assert decision.selected_model
    assert decision.features["probability_strong_better"] >= 0.0
    assert "ML router" in decision.explanation[0]
