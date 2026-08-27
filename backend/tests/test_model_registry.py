"""Tests for model registry and API."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.registry import ModelRegistry
from app.schemas.models import ModelCreateRequest, ModelTier, ModelType

client = TestClient(app)


@pytest.fixture
def temp_registry(tmp_path, monkeypatch):
    registry_path = tmp_path / "model_registry.json"
    registry = ModelRegistry(registry_path=registry_path)
    monkeypatch.setattr("app.models.registry._registry", registry)
    monkeypatch.setattr("app.api.models.get_model_registry", lambda: registry)
    monkeypatch.setattr("app.api.routing.get_model_registry", lambda: registry)
    return registry


def test_list_models_returns_defaults(temp_registry):
    response = client.get("/api/models")
    assert response.status_code == 200
    models = response.json()
    assert len(models) >= 3
    assert any(m["tier"] == "small" for m in models)


def test_get_model_by_id(temp_registry):
    response = client.get("/api/models/gpt-4o-mini")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "gpt-4o-mini"
    assert data["tier"] == "small"


def test_get_model_not_found(temp_registry):
    response = client.get("/api/models/nonexistent-model")
    assert response.status_code == 404


def test_enable_disable_model(temp_registry):
    response = client.post("/api/models/claude-3-haiku/enable")
    assert response.status_code == 200
    assert response.json()["enabled"] is True

    response = client.post("/api/models/claude-3-haiku/disable")
    assert response.status_code == 200
    assert response.json()["enabled"] is False


def test_create_model(temp_registry):
    payload = {
        "id": "custom-model",
        "name": "Custom Model",
        "provider": "openai_compatible",
        "type": "api",
        "tier": "medium",
        "input_cost_per_1m_tokens": 1.0,
        "output_cost_per_1m_tokens": 2.0,
        "context_window": 32000,
        "capabilities": ["general"],
        "enabled": True,
    }
    response = client.post("/api/models", json=payload)
    assert response.status_code == 201
    assert response.json()["id"] == "custom-model"


def test_router_status(temp_registry):
    response = client.get("/api/router/status")
    assert response.status_code == 200
    data = response.json()
    assert data["router_type"] == "rule_based"
    assert data["total_models"] >= 3
    assert data["enabled_models"] >= 1


def test_registry_get_by_tier(temp_registry):
    small_models = temp_registry.get_models_by_tier(ModelTier.SMALL)
    assert len(small_models) >= 1
    assert all(m.tier == ModelTier.SMALL for m in small_models)
