"""Tests for routing API."""

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
    monkeypatch.setattr("app.api.models.get_model_registry", lambda: registry)
    monkeypatch.setattr("app.api.routing.get_model_registry", lambda: registry)
    monkeypatch.setattr("app.router.rule_based.get_model_registry", lambda: registry)
    monkeypatch.setattr("app.router.policy.get_model_registry", lambda: registry)
    monkeypatch.setattr("app.services.chat.get_model_registry", lambda: registry)
    return registry


def test_route_endpoint(temp_registry):
    response = client.post("/api/route", json={"prompt": "Summarize this article in bullet points."})
    assert response.status_code == 200
    data = response.json()
    assert data["selected_model"]
    assert data["task_type"] == "summarization"
    assert "explanation" in data
    assert len(data["explanation"]) >= 3


def test_route_endpoint_with_config(temp_registry):
    response = client.post(
        "/api/route",
        json={
            "prompt": "Write a creative short story about space travel.",
            "configuration": {"quality_floor": 0.92},
        },
    )
    assert response.status_code == 200
    assert response.json()["estimated_quality"] >= 0.92
