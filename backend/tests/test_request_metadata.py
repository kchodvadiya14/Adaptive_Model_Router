"""Tests for request metadata, model preference, cost/latency constraints, and scoped
usage reporting (Phase 2 Step 6). Offline: mock providers only, judge disabled."""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from app.db.repository import list_routing_logs_for_usage, log_routing_event
from app.main import app
from app.models.registry import ModelRegistry
from app.providers.base import ProviderError, ProviderErrorCode
from app.providers.mock import MockProvider
from app.router import health
from app.router.capabilities import NoCapableModelError
from app.router.policy import estimate_prompt_cost
from app.schemas.chat import ChatMessage, ChatRequest
from app.schemas.models import ModelUpdateRequest
from app.schemas.usage import UsageFilters
from app.services.chat import ChatService
from app.services.usage import get_usage_summary

client = TestClient(app)

PROMPT = "What is the capital of France?"


# --- Fixtures -----------------------------------------------------------------------


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "metadata_test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    from app.config.settings import get_settings

    get_settings.cache_clear()
    from app.db import database

    database.init_db()
    yield db_path
    get_settings.cache_clear()


@pytest.fixture
def temp_registry(tmp_path, monkeypatch):
    registry = ModelRegistry(registry_path=tmp_path / "model_registry.json")
    monkeypatch.setattr("app.models.registry._registry", registry)
    monkeypatch.setattr("app.router.rule_based.get_model_registry", lambda: registry)
    monkeypatch.setattr("app.router.policy.get_model_registry", lambda: registry)
    monkeypatch.setattr("app.services.fallback.get_model_registry", lambda: registry)
    monkeypatch.setattr("app.services.chat.get_model_registry", lambda: registry)
    monkeypatch.setattr("app.api.models.get_model_registry", lambda: registry)
    monkeypatch.setattr("app.api.openai_compat.get_model_registry", lambda: registry)
    return registry


@pytest.fixture
def gateway_env(monkeypatch):
    for key, value in {
        "APP_ENV": "development",
        "EVALUATE_ON_CHAT": "false",
        "ROUTER_TYPE": "rule_based",
        "FALLBACK_ENABLED": "true",
        "FALLBACK_ESCALATION": "tier_up",
        "MAX_FALLBACK_ATTEMPTS": "3",
        "QUALITY_FLOOR": "0.90",
    }.items():
        monkeypatch.setenv(key, value)
    from app.config.settings import get_settings

    get_settings.cache_clear()


@pytest.fixture
def priced_registry(temp_registry):
    """Mock models are free by default; give them distinct prices so max_cost is testable.
    Latencies stay at the registry defaults: small 50ms, medium 75ms, strong 100ms.

    Once priced, the mocks are no longer the cheapest model in each tier, so the real
    API models (which would win primary-per-tier) are disabled to keep tests offline."""
    for model in temp_registry.list_models():
        if model.provider != "mock":
            temp_registry.set_enabled(model.id, enabled=False)
    temp_registry.update_model(
        "mock-echo", ModelUpdateRequest(input_cost_per_1m_tokens=1.0, output_cost_per_1m_tokens=2.0)
    )
    temp_registry.update_model(
        "mock-echo-medium", ModelUpdateRequest(input_cost_per_1m_tokens=5.0, output_cost_per_1m_tokens=10.0)
    )
    temp_registry.update_model(
        "mock-echo-strong", ModelUpdateRequest(input_cost_per_1m_tokens=20.0, output_cost_per_1m_tokens=40.0)
    )
    return temp_registry


def chat_request(**overrides) -> ChatRequest:
    fields = {"model": "auto", "messages": [ChatMessage(role="user", content=PROMPT)]}
    fields.update(overrides)
    return ChatRequest(**fields)


# --- Metadata propagation and request_id ---------------------------------------------


async def test_metadata_propagates_to_response_and_routing_log(temp_registry, temp_db, gateway_env):
    response = await ChatService().chat(
        chat_request(
            request_id="req-123",
            user_id="alice",
            session_id="sess-1",
            tags={"app": "support-bot", "env": "staging"},
        )
    )

    assert response.request_id == "req-123"
    rows = list_routing_logs_for_usage()
    assert len(rows) == 1
    row = rows[0]
    assert row["request_id"] == "req-123"
    assert row["user_id"] == "alice"
    assert row["session_id"] == "sess-1"
    assert row["tags_json"] == '{"app": "support-bot", "env": "staging"}'
    assert row["selected_model"] == response.model


async def test_request_id_generated_when_omitted(temp_registry, temp_db, gateway_env):
    first = await ChatService().chat(chat_request())
    second = await ChatService().chat(chat_request())

    assert re.fullmatch(r"[0-9a-f]{32}", first.request_id)
    assert first.request_id != second.request_id
    logged = [row["request_id"] for row in list_routing_logs_for_usage()]
    assert logged == [first.request_id, second.request_id]


def test_existing_clients_without_metadata_still_work(temp_registry, temp_db, gateway_env):
    response = client.post(
        "/api/chat",
        json={"model": "mock-echo", "messages": [{"role": "user", "content": "Hello"}]},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["model"] == "mock-echo"
    assert data["request_id"]
    row = list_routing_logs_for_usage()[0]
    assert row["user_id"] is None and row["tags_json"] is None and row["preferred_model"] is None


def test_openai_compat_maps_user_metadata_and_request_id_header(temp_registry, temp_db, gateway_env):
    response = client.post(
        "/v1/chat/completions",
        headers={"X-Request-ID": "oa-req-7"},
        json={
            "model": "mock-echo",
            "messages": [{"role": "user", "content": "Hello"}],
            "user": "bob",
            "metadata": {"team": "search"},
        },
    )
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "oa-req-7"
    row = list_routing_logs_for_usage()[0]
    assert row["request_id"] == "oa-req-7"
    assert row["user_id"] == "bob"
    assert row["tags_json"] == '{"team": "search"}'


# --- Preferred model -----------------------------------------------------------------


async def test_preferred_model_is_selected_when_eligible(temp_registry, temp_db, gateway_env):
    response = await ChatService().chat(chat_request(preferred_model="mock-echo-strong"))

    assert response.model == "mock-echo-strong"
    assert response.routing.preferred_model == "mock-echo-strong"
    assert response.routing.preferred_model_honored is True
    assert "Preferred model" in response.routing.reason
    assert list_routing_logs_for_usage()[0]["preferred_model"] == "mock-echo-strong"


async def test_preferred_model_blocked_by_capability(temp_registry, temp_db, gateway_env):
    temp_registry.update_model("mock-echo-medium", ModelUpdateRequest(supports_tools=True))

    response = await ChatService().chat(
        chat_request(
            preferred_model="mock-echo",  # no tool support
            tools=[{"type": "function", "function": {"name": "lookup"}}],
        )
    )

    assert response.model == "mock-echo-medium"
    assert response.routing.preferred_model_honored is False
    assert any(
        "Preferred model 'mock-echo' not used" in line and "tool" in line
        for line in response.routing.explanation
    )


async def test_preferred_model_blocked_by_health(temp_registry, temp_db, gateway_env):
    config = health.get_health_config()
    for _ in range(config.failure_threshold):
        health.record_failure("mock-echo-strong", "mock", "simulated outage", config=config)

    response = await ChatService().chat(chat_request(preferred_model="mock-echo-strong"))

    assert response.model != "mock-echo-strong"
    assert response.routing.preferred_model_honored is False
    assert any(
        "Preferred model 'mock-echo-strong' not used" in line and "temporarily unavailable" in line
        for line in response.routing.explanation
    )


async def test_preferred_model_blocked_by_constraint(priced_registry, temp_db, gateway_env):
    response = await ChatService().chat(
        chat_request(preferred_model="mock-echo-strong", max_latency_ms=80)
    )

    assert response.model != "mock-echo-strong"
    assert response.routing.preferred_model_honored is False
    assert any("max_latency_ms" in line for line in response.routing.explanation)


def test_unknown_preferred_model_returns_404(temp_registry, temp_db, gateway_env):
    response = client.post(
        "/api/chat",
        json={"model": "auto", "preferred_model": "no-such-model", "messages": [{"role": "user", "content": PROMPT}]},
    )
    assert response.status_code == 404
    assert "no-such-model" in response.json()["detail"]


def test_disabled_preferred_model_returns_404(temp_registry, temp_db, gateway_env):
    temp_registry.set_enabled("mock-echo-strong", enabled=False)
    response = client.post(
        "/api/chat",
        json={"model": "auto", "preferred_model": "mock-echo-strong", "messages": [{"role": "user", "content": PROMPT}]},
    )
    assert response.status_code == 404
    assert "disabled" in response.json()["detail"]


def test_preferred_model_conflicting_with_pinned_model_is_rejected(temp_registry, temp_db, gateway_env):
    response = client.post(
        "/api/chat",
        json={"model": "mock-echo", "preferred_model": "mock-echo-strong", "messages": [{"role": "user", "content": PROMPT}]},
    )
    assert response.status_code == 422


async def test_preferred_model_keeps_quality_escalation(temp_registry, temp_db, gateway_env, monkeypatch):
    """A preference only picks the starting model; the existing quality escalation
    still runs on its response."""
    monkeypatch.setenv("EVALUATE_ON_CHAT", "true")
    monkeypatch.setenv("FALLBACK_ON_QUALITY_BELOW", "0.85")
    from app.config.settings import get_settings

    get_settings.cache_clear()

    async def low_for_small(self, prompt, response):
        return 0.40 if response.startswith("[Mock Mock Echo (Local)]") else 0.93

    monkeypatch.setattr(ChatService, "_evaluate_response_quality", low_for_small)

    response = await ChatService().chat(chat_request(preferred_model="mock-echo"))

    assert response.routing.preferred_model_honored is True
    assert response.model == "mock-echo-medium"
    assert response.fallback.escalation_reason == "quality_below_threshold"


# --- Cost and latency constraints ----------------------------------------------------


async def test_max_cost_excludes_expensive_tier(priced_registry, temp_db, gateway_env, monkeypatch):
    # A 0.95 floor is only met by the strong tier, so unconstrained routing picks strong.
    monkeypatch.setenv("QUALITY_FLOOR", "0.95")
    from app.config.settings import get_settings

    get_settings.cache_clear()

    unconstrained = await ChatService().chat(chat_request())
    assert unconstrained.model == "mock-echo-strong"

    strong_cost = estimate_prompt_cost(priced_registry.get_model("mock-echo-strong"), PROMPT)
    medium_cost = estimate_prompt_cost(priced_registry.get_model("mock-echo-medium"), PROMPT)
    assert medium_cost < strong_cost

    constrained = await ChatService().chat(chat_request(max_cost=medium_cost))
    assert constrained.model == "mock-echo-medium"
    assert any("exceeds max_cost" in line for line in constrained.routing.explanation)


async def test_max_latency_excludes_slow_tier(temp_registry, temp_db, gateway_env, monkeypatch):
    monkeypatch.setenv("QUALITY_FLOOR", "0.95")
    from app.config.settings import get_settings

    get_settings.cache_clear()

    response = await ChatService().chat(chat_request(max_latency_ms=80))  # strong is 100ms

    assert response.model == "mock-echo-medium"
    assert any("exceeds max_latency_ms" in line for line in response.routing.explanation)


async def test_impossible_constraint_raises_structured_error(temp_registry, temp_db, gateway_env):
    with pytest.raises(NoCapableModelError) as exc_info:
        await ChatService().chat(chat_request(max_latency_ms=10))

    error = exc_info.value
    assert error.constraints.max_latency_ms == 10
    assert len(error.excluded) == 3
    assert all("max_latency_ms" in item.reason for item in error.excluded)
    assert "average latency at most 10ms" in str(error)


def test_impossible_constraint_via_api_returns_422(temp_registry, temp_db, gateway_env):
    response = client.post(
        "/api/chat",
        json={"model": "auto", "max_latency_ms": 10, "messages": [{"role": "user", "content": PROMPT}]},
    )
    assert response.status_code == 422
    assert "max_latency_ms" in response.json()["detail"]


def test_pinned_model_breaking_constraint_returns_422(priced_registry, temp_db, gateway_env):
    response = client.post(
        "/api/chat",
        json={"model": "mock-echo-strong", "max_cost": 0.0, "messages": [{"role": "user", "content": PROMPT}]},
    )
    assert response.status_code == 422
    assert "max_cost" in response.json()["detail"]


async def test_constraint_limits_provider_error_fallback(temp_registry, temp_db, gateway_env, monkeypatch):
    original_generate = MockProvider.generate

    async def small_times_out(self, request):
        if self.model.id == "mock-echo":
            raise ProviderError("Simulated timeout", code=ProviderErrorCode.TIMEOUT)
        return await original_generate(self, request)

    monkeypatch.setattr(MockProvider, "generate", small_times_out)

    # Without a constraint, the existing fallback escalates to medium.
    unconstrained = await ChatService().chat(chat_request(model="mock-echo"))
    assert unconstrained.model == "mock-echo-medium"

    # medium (75ms) and strong (100ms) both break max_latency_ms=60: nothing to fall back to.
    with pytest.raises(ProviderError) as exc_info:
        await ChatService().chat(chat_request(model="mock-echo", max_latency_ms=60))
    assert exc_info.value.code == ProviderErrorCode.TIMEOUT


async def test_constraint_limits_quality_escalation(temp_registry, temp_db, gateway_env, monkeypatch):
    monkeypatch.setenv("EVALUATE_ON_CHAT", "true")
    monkeypatch.setenv("FALLBACK_ON_QUALITY_BELOW", "0.85")
    from app.config.settings import get_settings

    get_settings.cache_clear()

    async def always_low(self, prompt, response):
        return 0.40

    monkeypatch.setattr(ChatService, "_evaluate_response_quality", always_low)

    response = await ChatService().chat(chat_request(model="mock-echo", max_latency_ms=60))

    assert response.model == "mock-echo"  # escalation targets break the constraint
    assert response.fallback is None


def test_route_api_accepts_preference_and_constraints(priced_registry, temp_db, gateway_env):
    response = client.post(
        "/api/route",
        json={"prompt": PROMPT, "preferred_model": "mock-echo-medium", "max_latency_ms": 90},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["selected_model"] == "mock-echo-medium"
    assert data["preferred_model_honored"] is True

    impossible = client.post("/api/route", json={"prompt": PROMPT, "max_cost": 0.0})
    assert impossible.status_code == 422


# --- Usage aggregation and filtering -------------------------------------------------


def _seed(**overrides):
    fields = dict(
        prompt=PROMPT,
        task_type="general_qa",
        difficulty=0.2,
        router_type="rule_based",
        selected_model="mock-echo",
        model_tier="small",
        estimated_cost=0.0,
        actual_cost=0.0,
        estimated_quality=None,
        actual_quality=None,
        latency_ms=100.0,
        routed=True,
        strong_baseline_cost=0.0,
    )
    fields.update(overrides)
    log_routing_event(**fields)


@pytest.fixture
def seeded_usage(temp_db):
    _seed(request_id="r1", user_id="alice", session_id="s1", tags={"app": "chat", "env": "prod"},
          selected_model="mock-echo", actual_cost=0.001, latency_ms=100.0)
    _seed(request_id="r2", user_id="alice", session_id="s2", tags={"app": "chat"},
          selected_model="mock-echo-medium", model_tier="medium", actual_cost=0.004, latency_ms=200.0,
          fallback_used=True, fallback_attempts=2, fallback_reason="provider_error")
    _seed(request_id="r3", user_id="bob", session_id="s3", tags={"app": "search"},
          selected_model="mock-echo", actual_cost=0.002, latency_ms=300.0)
    _seed(request_id="r4")  # a pre-Step-6 style row: no user, session or tags


def test_usage_totals_and_breakdowns(seeded_usage):
    summary = get_usage_summary(UsageFilters())

    assert summary.total_requests == 4
    assert summary.successful_requests == 4
    assert summary.fallback_requests == 1
    assert summary.total_estimated_cost == pytest.approx(0.007)
    assert summary.average_latency_ms == pytest.approx(175.0)

    by_user = {entry.key: entry for entry in summary.by_user}
    assert by_user["alice"].total_requests == 2
    assert by_user["alice"].fallback_requests == 1
    assert by_user["alice"].total_estimated_cost == pytest.approx(0.005)
    assert by_user["alice"].average_latency_ms == pytest.approx(150.0)
    assert by_user["bob"].total_requests == 1
    assert by_user["(none)"].total_requests == 1

    by_model = {entry.key: entry for entry in summary.by_model}
    assert by_model["mock-echo"].total_requests == 3
    assert by_model["mock-echo-medium"].total_requests == 1

    by_tag = {entry.key: entry for entry in summary.by_tag}
    assert by_tag["app=chat"].total_requests == 2
    assert by_tag["app=search"].total_requests == 1
    assert by_tag["env=prod"].total_requests == 1
    assert sum(1 for key in by_tag if key.startswith("app=")) == 2  # untagged row counts in no tag group


def test_usage_api_filters_by_user(seeded_usage):
    data = client.get("/api/usage", params={"user_id": "alice"}).json()
    assert data["total_requests"] == 2
    assert [entry["key"] for entry in data["by_user"]] == ["alice"]
    assert data["filters"]["user_id"] == "alice"


def test_usage_api_filters_by_session(seeded_usage):
    data = client.get("/api/usage", params={"session_id": "s3"}).json()
    assert data["total_requests"] == 1
    assert data["by_user"][0]["key"] == "bob"


def test_usage_api_filters_by_model(seeded_usage):
    data = client.get("/api/usage", params={"model_id": "mock-echo-medium"}).json()
    assert data["total_requests"] == 1
    assert data["fallback_requests"] == 1


def test_usage_api_filters_by_tag_key_and_value(seeded_usage):
    by_key = client.get("/api/usage", params={"tag_key": "env"}).json()
    assert by_key["total_requests"] == 1

    by_value = client.get("/api/usage", params={"tag_key": "app", "tag_value": "chat"}).json()
    assert by_value["total_requests"] == 2
    assert by_value["total_estimated_cost"] == pytest.approx(0.005)

    combined = client.get("/api/usage", params={"user_id": "bob", "tag_key": "app", "tag_value": "chat"}).json()
    assert combined["total_requests"] == 0
    assert combined["average_latency_ms"] == 0.0


def test_usage_api_rejects_tag_value_without_key(seeded_usage):
    response = client.get("/api/usage", params={"tag_value": "chat"})
    assert response.status_code == 422


async def test_usage_reflects_real_chat_requests(temp_registry, temp_db, gateway_env):
    await ChatService().chat(chat_request(user_id="carol", model="mock-echo", tags={"app": "demo"}))
    await ChatService().chat(chat_request(user_id="carol", model="mock-echo-medium"))
    await ChatService().chat(chat_request(user_id="dave"))

    data = client.get("/api/usage", params={"user_id": "carol"}).json()
    assert data["total_requests"] == 2
    assert {entry["key"] for entry in data["by_model"]} == {"mock-echo", "mock-echo-medium"}
    assert [entry["key"] for entry in data["by_tag"]] == ["app=demo"]
