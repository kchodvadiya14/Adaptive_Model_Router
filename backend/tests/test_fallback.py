"""Tests for fallback chain and cost/latency optimization."""

import pytest

from app.models.registry import ModelRegistry
from app.providers.base import GenerationRequest, ProviderError, ProviderErrorCode
from app.providers.mock import MockProvider
from app.router.policy import RoutingPolicyConfig, evaluate_tiers, select_model_from_evaluations
from app.router.task_classifier import TaskType
from app.schemas.models import ModelUpdateRequest
from app.services.fallback import FallbackExecutor, build_fallback_chain, build_fallback_info
from app.schemas.chat import FallbackAttemptRecord


@pytest.fixture
def temp_registry(tmp_path, monkeypatch):
    registry_path = tmp_path / "model_registry.json"
    registry = ModelRegistry(registry_path=registry_path)
    monkeypatch.setattr("app.models.registry._registry", registry)
    monkeypatch.setattr("app.services.fallback.get_model_registry", lambda: registry)
    monkeypatch.setattr("app.services.chat.get_model_registry", lambda: registry)
    monkeypatch.setattr("app.router.rule_based.get_model_registry", lambda: registry)
    monkeypatch.setattr("app.router.policy.get_model_registry", lambda: registry)
    return registry


def test_build_fallback_chain_tier_up(temp_registry):
    chain = build_fallback_chain("mock-echo", temp_registry, escalation="tier_up", max_attempts=3)
    assert chain == ["mock-echo", "mock-echo-medium", "mock-echo-strong"]


def test_build_fallback_chain_strong_only(temp_registry):
    chain = build_fallback_chain("mock-echo", temp_registry, escalation="strong_only", max_attempts=2)
    assert chain == ["mock-echo", "mock-echo-strong"]


def test_build_fallback_info_detects_escalation():
    info = build_fallback_info(
        "mock-echo",
        "mock-echo-medium",
        [
            FallbackAttemptRecord(
                model_id="mock-echo",
                model_tier="small",
                success=False,
                reason="timeout",
            ),
            FallbackAttemptRecord(
                model_id="mock-echo-medium",
                model_tier="medium",
                success=True,
                reason="success",
            ),
        ],
    )
    assert info is not None
    assert info.used is True
    assert info.original_model == "mock-echo"
    assert info.final_model == "mock-echo-medium"
    assert info.escalation_reason == "provider_error"


@pytest.mark.asyncio
async def test_fallback_executor_escalates_on_provider_error(temp_registry, monkeypatch):
    original_generate = MockProvider.generate
    state = {"failed": False}

    async def flaky_generate(self, request):
        if self.model.id == "mock-echo" and not state["failed"]:
            state["failed"] = True
            raise ProviderError("Simulated timeout", code=ProviderErrorCode.TIMEOUT)
        return await original_generate(self, request)

    monkeypatch.setattr(MockProvider, "generate", flaky_generate)

    executor = FallbackExecutor(registry=temp_registry)
    request = GenerationRequest(messages=[{"role": "user", "content": "Hello fallback test"}])
    model, generation, attempts = await executor.generate_with_fallback("mock-echo", request)

    assert model.id == "mock-echo-medium"
    assert generation.content
    assert len(attempts) == 2
    assert attempts[0].success is False
    assert attempts[1].success is True


def test_select_model_prefers_lowest_latency(temp_registry):
    temp_registry.update_model("mock-echo", ModelUpdateRequest(avg_latency_ms=500))
    temp_registry.update_model("mock-echo-medium", ModelUpdateRequest(avg_latency_ms=100))

    evaluations = evaluate_tiers(
        "What is the capital of France?",
        TaskType.GENERAL_QA,
        difficulty=0.2,
        registry=temp_registry,
    )
    policy = RoutingPolicyConfig(quality_floor=0.85, cost_priority=0.0, latency_priority=1.0)
    selected = select_model_from_evaluations(evaluations, policy)
    assert selected.model is not None
    assert selected.model.id == "mock-echo-medium"


def test_select_model_prefers_lowest_cost(temp_registry):
    temp_registry.update_model("mock-echo", ModelUpdateRequest(avg_latency_ms=50))
    temp_registry.update_model("mock-echo-medium", ModelUpdateRequest(avg_latency_ms=50))

    evaluations = evaluate_tiers(
        "What is the capital of France?",
        TaskType.GENERAL_QA,
        difficulty=0.2,
        registry=temp_registry,
    )
    policy = RoutingPolicyConfig(quality_floor=0.85, cost_priority=1.0, latency_priority=0.0)
    selected = select_model_from_evaluations(evaluations, policy)
    assert selected.model is not None
    assert selected.model.id == "mock-echo"


def test_router_status_includes_fallback_settings(temp_registry):
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    response = client.get("/api/router/status")
    assert response.status_code == 200
    data = response.json()
    assert "fallback_enabled" in data
    assert data["max_fallback_attempts"] >= 1


@pytest.mark.asyncio
async def test_chat_api_returns_fallback_metadata(temp_registry, monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app

    original_generate = MockProvider.generate
    state = {"failed": False}

    async def flaky_generate(self, request):
        if self.model.id == "mock-echo" and not state["failed"]:
            state["failed"] = True
            raise ProviderError("Simulated timeout", code=ProviderErrorCode.TIMEOUT)
        return await original_generate(self, request)

    monkeypatch.setattr(MockProvider, "generate", flaky_generate)
    monkeypatch.setenv("EVALUATE_ON_CHAT", "false")
    from app.config.settings import get_settings

    get_settings.cache_clear()

    client = TestClient(app)
    response = client.post(
        "/api/chat",
        json={
            "model": "mock-echo",
            "messages": [{"role": "user", "content": "Test fallback metadata"}],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["fallback"] is not None
    assert data["fallback"]["used"] is True
    assert data["fallback"]["final_model"] == "mock-echo-medium"
    assert len(data["fallback"]["attempts"]) == 2
