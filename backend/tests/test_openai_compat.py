"""Tests for OpenAI-compatible /v1 API."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.registry import ModelRegistry
from app.schemas.chat import ChatResponse, CostBreakdown, TokenUsage
from app.utils.openai_compat import to_chat_request, to_openai_response
from app.schemas.openai import OpenAIChatCompletionRequest, OpenAIMessage

client = TestClient(app)


@pytest.fixture
def temp_registry(tmp_path, monkeypatch):
    registry_path = tmp_path / "model_registry.json"
    registry = ModelRegistry(registry_path=registry_path)
    monkeypatch.setattr("app.models.registry._registry", registry)
    monkeypatch.setattr("app.api.models.get_model_registry", lambda: registry)
    monkeypatch.setattr("app.api.openai_compat.get_model_registry", lambda: registry)
    monkeypatch.setattr("app.api.routing.get_model_registry", lambda: registry)
    monkeypatch.setattr("app.services.chat.get_model_registry", lambda: registry)
    return registry


def test_v1_models_includes_auto(temp_registry):
    response = client.get("/v1/models")
    assert response.status_code == 200
    data = response.json()
    assert data["object"] == "list"
    ids = {item["id"] for item in data["data"]}
    assert "auto" in ids
    assert "mock-echo" in ids


def test_v1_get_model_auto(temp_registry):
    response = client.get("/v1/models/auto")
    assert response.status_code == 200
    assert response.json()["id"] == "auto"


def test_v1_chat_completions_mock_model(temp_registry):
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "mock-echo",
            "messages": [{"role": "user", "content": "Hello OpenAI compat"}],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["object"] == "chat.completion"
    assert data["model"] == "mock-echo"
    assert data["choices"][0]["message"]["role"] == "assistant"
    assert "Hello OpenAI compat" in data["choices"][0]["message"]["content"]
    assert data["usage"]["total_tokens"] > 0
    assert data["router"] is None


def test_v1_chat_completions_auto_routing(temp_registry, monkeypatch):
    monkeypatch.setattr("app.router.rule_based.get_model_registry", lambda: temp_registry)
    monkeypatch.setattr("app.router.policy.get_model_registry", lambda: temp_registry)
    monkeypatch.setenv("EVALUATE_ON_CHAT", "false")
    from app.config.settings import get_settings

    get_settings.cache_clear()

    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "auto",
            "messages": [{"role": "user", "content": "What is the capital of France?"}],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["model"] in {"mock-echo", "mock-echo-medium", "mock-echo-strong"}
    assert data["router"] is not None
    assert data["router"]["routed"] is True
    assert data["router"]["task_type"] == "general_qa"


def test_v1_chat_completions_auto_case_insensitive(temp_registry, monkeypatch):
    monkeypatch.setattr("app.router.rule_based.get_model_registry", lambda: temp_registry)
    monkeypatch.setattr("app.router.policy.get_model_registry", lambda: temp_registry)
    monkeypatch.setenv("EVALUATE_ON_CHAT", "false")
    from app.config.settings import get_settings

    get_settings.cache_clear()

    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "AUTO",
            "messages": [{"role": "user", "content": "Capital of France?"}],
        },
    )
    assert response.status_code == 200
    assert response.json()["router"]["routed"] is True


def test_v1_rejects_streaming(temp_registry):
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "mock-echo",
            "messages": [{"role": "user", "content": "Hi"}],
            "stream": True,
        },
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "streaming_not_supported"


def test_v1_api_key_required_when_configured(temp_registry, monkeypatch):
    monkeypatch.setenv("ROUTER_API_KEY", "test-secret-key")
    from app.config.settings import get_settings

    get_settings.cache_clear()

    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "mock-echo",
            "messages": [{"role": "user", "content": "Hi"}],
        },
    )
    assert response.status_code == 401

    authed = client.post(
        "/v1/chat/completions",
        json={
            "model": "mock-echo",
            "messages": [{"role": "user", "content": "Hi"}],
        },
        headers={"Authorization": "Bearer test-secret-key"},
    )
    assert authed.status_code == 200

    get_settings.cache_clear()


def test_v1_quality_floor_header(temp_registry, monkeypatch):
    monkeypatch.setattr("app.router.rule_based.get_model_registry", lambda: temp_registry)
    monkeypatch.setattr("app.router.policy.get_model_registry", lambda: temp_registry)
    monkeypatch.setenv("EVALUATE_ON_CHAT", "false")
    from app.config.settings import get_settings

    get_settings.cache_clear()

    response = client.post(
        "/v1/chat/completions",
        headers={"X-Quality-Floor": "0.95"},
        json={
            "model": "auto",
            "messages": [{"role": "user", "content": "Explain quantum computing in detail."}],
        },
    )
    assert response.status_code == 200
    assert response.json()["router"]["estimated_quality"] >= 0.95


def test_converter_to_openai_response_includes_router_metadata():
    chat = ChatResponse(
        content="Answer",
        model="mock-echo-medium",
        model_name="Mock Echo Medium",
        provider="mock",
        tier="medium",
        usage=TokenUsage(input_tokens=5, output_tokens=10, total_tokens=15),
        cost=CostBreakdown(input_cost=0, output_cost=0, total_cost=0),
        latency_ms=50,
        routed=True,
        routing=None,
    )
    openai_response = to_openai_response(chat)
    assert openai_response.model == "mock-echo-medium"
    assert openai_response.choices[0].message.content == "Answer"


def test_converter_to_chat_request_skips_empty_messages():
    request = OpenAIChatCompletionRequest(
        model="auto",
        messages=[
            OpenAIMessage(role="user", content="  "),
            OpenAIMessage(role="user", content="Valid prompt"),
        ],
    )
    chat_request = to_chat_request(request)
    assert len(chat_request.messages) == 1
    assert chat_request.model == "auto"
