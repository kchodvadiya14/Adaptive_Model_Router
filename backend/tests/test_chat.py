"""Tests for chat API."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.registry import ModelRegistry
from app.schemas.models import ModelTier

client = TestClient(app)


@pytest.fixture
def temp_registry(tmp_path, monkeypatch):
    registry_path = tmp_path / "model_registry.json"
    registry = ModelRegistry(registry_path=registry_path)
    monkeypatch.setattr("app.models.registry._registry", registry)
    monkeypatch.setattr("app.api.models.get_model_registry", lambda: registry)
    monkeypatch.setattr("app.api.routing.get_model_registry", lambda: registry)
    monkeypatch.setattr("app.services.chat.get_model_registry", lambda: registry)
    return registry


def test_chat_with_mock_model(temp_registry):
    response = client.post(
        "/api/chat",
        json={
            "model": "mock-echo",
            "messages": [{"role": "user", "content": "Explain recursion briefly"}],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "Explain recursion briefly" in data["content"]
    assert data["model"] == "mock-echo"
    assert data["provider"] == "mock"
    assert data["tier"] == "small"
    assert data["usage"]["total_tokens"] > 0
    assert data["cost"]["total_cost"] == 0.0
    assert data["latency_ms"] >= 0


def test_chat_model_not_found(temp_registry):
    response = client.post(
        "/api/chat",
        json={
            "model": "does-not-exist",
            "messages": [{"role": "user", "content": "Hi"}],
        },
    )
    assert response.status_code == 404


def test_chat_disabled_model(temp_registry):
    temp_registry.set_enabled("mock-echo", enabled=False)
    response = client.post(
        "/api/chat",
        json={
            "model": "mock-echo",
            "messages": [{"role": "user", "content": "Hi"}],
        },
    )
    assert response.status_code == 404


def test_chat_openai_without_api_key(temp_registry):
    response = client.post(
        "/api/chat",
        json={
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "Hi"}],
        },
    )
    assert response.status_code == 503
    assert "not configured" in response.json()["detail"]


def test_chat_all_mock_tiers(temp_registry):
    tier_models = {
        ModelTier.SMALL: "mock-echo",
        ModelTier.MEDIUM: "mock-echo-medium",
        ModelTier.STRONG: "mock-echo-strong",
    }
    for tier, model_id in tier_models.items():
        response = client.post(
            "/api/chat",
            json={
                "model": model_id,
                "messages": [{"role": "user", "content": f"Test {tier.value}"}],
            },
        )
        assert response.status_code == 200
        assert response.json()["tier"] == tier.value


def test_chat_auto_routing_uses_router(temp_registry, monkeypatch):
    monkeypatch.setattr("app.router.rule_based.get_model_registry", lambda: temp_registry)
    monkeypatch.setattr("app.router.policy.get_model_registry", lambda: temp_registry)
    monkeypatch.setenv("EVALUATE_ON_CHAT", "false")
    from app.config.settings import get_settings

    get_settings.cache_clear()

    response = client.post(
        "/api/chat",
        json={
            "model": "auto",
            "messages": [{"role": "user", "content": "What is the capital of France?"}],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["routed"] is True
    assert data["routing"] is not None
    assert data["routing"]["selected_model"] == data["model"]
    assert data["routing"]["task_type"] == "general_qa"
