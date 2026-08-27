"""Tests for preference dataset pipeline."""

import pytest
from fastapi.testclient import TestClient

from app.datasets.generator import compute_preference_labels
from app.main import app
from app.models.registry import ModelRegistry

client = TestClient(app)


@pytest.fixture
def temp_registry(tmp_path, monkeypatch):
    registry_path = tmp_path / "model_registry.json"
    registry = ModelRegistry(registry_path=registry_path)
    monkeypatch.setattr("app.models.registry._registry", registry)
    monkeypatch.setattr("app.datasets.generator.get_model_registry", lambda: registry)
    monkeypatch.setattr("app.router.rule_based.get_model_registry", lambda: registry)
    monkeypatch.setattr("app.router.policy.get_model_registry", lambda: registry)
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
def sample_source(tmp_path):
    path = tmp_path / "source.json"
    path.write_text(
        '[{"id":"p1","prompt":"Explain Python lists.","category":"general_qa"},'
        '{"id":"p2","prompt":"Debug this code snippet.","category":"debugging"}]',
        encoding="utf-8",
    )
    return str(path)


def test_compute_preference_labels():
    preferred, small_ok, medium_ok, strong_ok = compute_preference_labels(
        small_score=0.82,
        medium_score=0.91,
        strong_score=0.95,
        quality_floor=0.90,
    )
    assert preferred == "medium"
    assert small_ok is False
    assert medium_ok is True
    assert strong_ok is True


@pytest.mark.asyncio
async def test_dataset_generator(temp_registry, temp_storage, sample_source):
    from app.datasets.generator import PreferenceDatasetGenerator

    generator = PreferenceDatasetGenerator()
    manifest = await generator.generate(
        source_path=sample_source,
        name="test_dataset",
        quality_floor=0.85,
        max_prompts=2,
    )
    assert manifest.record_count == 2
    assert manifest.id


def test_dataset_list_and_get_api(temp_registry, temp_storage, sample_source):
    from app.datasets.generator import PreferenceDatasetGenerator
    import asyncio

    generator = PreferenceDatasetGenerator()
    manifest = asyncio.run(
        generator.generate(
            source_path=sample_source,
            name="list_api_dataset",
            quality_floor=0.85,
            max_prompts=2,
        )
    )

    list_response = client.get("/api/dataset")
    assert list_response.status_code == 200
    assert any(item["id"] == manifest.id for item in list_response.json())

    detail = client.get(f"/api/dataset/{manifest.id}")
    assert detail.status_code == 200
    assert detail.json()["total"] == 2


def test_human_evaluation(temp_registry, temp_storage, sample_source):
    from app.datasets.generator import PreferenceDatasetGenerator

    generator = PreferenceDatasetGenerator()

    import asyncio

    manifest = asyncio.run(
        generator.generate(
            source_path=sample_source,
            name="human_eval",
            quality_floor=0.85,
            max_prompts=1,
        )
    )
    record_id = "p1"
    response = client.post(
        f"/api/dataset/{manifest.id}/human-eval",
        json={
            "record_id": record_id,
            "small_score": 0.95,
            "preferred_model": "small",
            "notes": "Human review override",
        },
    )
    assert response.status_code == 200
    assert response.json()["preferred_model"] == "small"
    assert response.json()["evaluation_source"] == "human"
