"""Tests for end-to-end request deadlines (Phase 2 Step 7).

Offline: mock providers with injected delays, judge replaced by async stubs.

Timing design: each request carries tens to hundreds of ms of synchronous overhead
(SQLite health/log writes, routing) that no deadline can cancel, and that grows under
suite load. So every test is built to assert *which stage* the budget runs out in, with
several hundred ms of slack on each side, rather than on tight wall-clock numbers.
Slow calls use multi-second delays; they are cancelled at the deadline, so they don't
slow the suite down.
"""

from __future__ import annotations

import asyncio
import time

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.registry import ModelRegistry
from app.providers.base import ProviderError, ProviderErrorCode
from app.providers.mock import MockProvider
from app.router import health
from app.router.health import CircuitState
from app.schemas.chat import ChatMessage, ChatRequest
from app.schemas.models import ModelUpdateRequest
from app.services.chat import ChatService
from app.services.deadline import RequestDeadline, RequestTimeoutError

client = TestClient(app)

PROMPT = "What is the capital of France?"
SMALL_PREFIX = "[Mock Mock Echo (Local)]"
SLOW = 5.0  # seconds; always cancelled by the deadline in these tests


# --- Fixtures -----------------------------------------------------------------------


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "deadline_test.db"
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
    monkeypatch.setattr("app.api.openai_compat.get_model_registry", lambda: registry)
    return registry


def set_env(monkeypatch, **values):
    for key, value in values.items():
        monkeypatch.setenv(key, str(value))
    from app.config.settings import get_settings

    get_settings.cache_clear()


@pytest.fixture
def gateway_env(monkeypatch):
    set_env(
        monkeypatch,
        APP_ENV="development",
        EVALUATE_ON_CHAT="false",
        ROUTER_TYPE="rule_based",
        FALLBACK_ENABLED="true",
        FALLBACK_ESCALATION="tier_up",
        MAX_FALLBACK_ATTEMPTS="3",
        FALLBACK_ON_QUALITY_BELOW="0.85",
        REQUEST_MIN_ATTEMPT_BUDGET_MS="10",
    )


class ProviderScript:
    """Per-model delay and optional error for MockProvider.generate; records calls."""

    def __init__(self, monkeypatch):
        self.delays: dict[str, float] = {}
        self.errors: dict[str, ProviderErrorCode] = {}
        self.calls: list[str] = []
        original_generate = MockProvider.generate
        script = self

        async def scripted(provider_self, request):
            model_id = provider_self.model.id
            script.calls.append(model_id)
            await asyncio.sleep(script.delays.get(model_id, 0.0))
            if model_id in script.errors:
                code = script.errors[model_id]
                raise ProviderError(f"Simulated {code.value}", code=code)
            return await original_generate(provider_self, request)

        monkeypatch.setattr(MockProvider, "generate", scripted)


@pytest.fixture
def providers(monkeypatch):
    return ProviderScript(monkeypatch)


def pinned(model: str = "mock-echo", **overrides) -> ChatRequest:
    fields = {"model": model, "messages": [ChatMessage(role="user", content=PROMPT)]}
    fields.update(overrides)
    return ChatRequest(**fields)


# --- Baseline behavior ---------------------------------------------------------------


async def test_no_timeout_preserves_existing_behavior(temp_registry, temp_db, gateway_env, providers):
    providers.delays["mock-echo"] = 0.3  # would blow any small timeout

    response = await ChatService().chat(pinned())

    assert response.model == "mock-echo"
    assert response.fallback is None


async def test_generation_completes_within_timeout(temp_registry, temp_db, gateway_env, providers):
    response = await ChatService().chat(pinned(timeout_ms=5000))

    assert response.model == "mock-echo"
    assert response.content.startswith(SMALL_PREFIX)


# --- Generation and fallback ---------------------------------------------------------


async def test_generation_exceeding_timeout_is_cancelled(temp_registry, temp_db, gateway_env, providers):
    providers.delays["mock-echo"] = SLOW

    started = time.monotonic()
    with pytest.raises(RequestTimeoutError) as exc_info:
        await ChatService().chat(pinned(timeout_ms=400, request_id="req-gen"))
    wall_ms = (time.monotonic() - started) * 1000

    error = exc_info.value
    assert error.stage == "generation"
    assert error.model_id == "mock-echo"
    assert error.request_id == "req-gen"
    assert error.started is True
    assert error.timeout_ms == 400
    assert error.elapsed_ms >= 350
    assert wall_ms < 3000  # cancelled at the deadline, not after the 5s provider call
    assert providers.calls == ["mock-echo"]  # a deadline is not a reason to fall back


async def test_fallback_gets_only_the_remaining_budget(temp_registry, temp_db, gateway_env, providers):
    # small fails after 700ms; medium needs ~1250ms. A fresh 1500ms budget per attempt
    # would let medium finish; the shared budget leaves it at most ~800ms.
    providers.delays["mock-echo"] = 0.7
    providers.errors["mock-echo"] = ProviderErrorCode.TIMEOUT  # genuine retryable failure
    providers.delays["mock-echo-medium"] = 1.2

    with pytest.raises(RequestTimeoutError) as exc_info:
        await ChatService().chat(pinned(timeout_ms=1500))

    error = exc_info.value
    assert error.stage == "fallback"
    assert error.model_id == "mock-echo-medium"
    assert error.started is True
    assert providers.calls == ["mock-echo", "mock-echo-medium"]


async def test_fallback_succeeds_when_remaining_budget_suffices(temp_registry, temp_db, gateway_env, providers):
    providers.errors["mock-echo"] = ProviderErrorCode.TIMEOUT

    response = await ChatService().chat(pinned(timeout_ms=5000))

    assert response.model == "mock-echo-medium"
    assert response.fallback.escalation_reason == "provider_error"


async def test_fallback_not_started_when_budget_exhausted(
    temp_registry, temp_db, gateway_env, providers, monkeypatch
):
    # After small's 1000ms failure at most ~1000ms is left, below the 1200ms minimum.
    set_env(monkeypatch, REQUEST_MIN_ATTEMPT_BUDGET_MS="1200")
    providers.delays["mock-echo"] = 1.0
    providers.errors["mock-echo"] = ProviderErrorCode.NETWORK_ERROR

    with pytest.raises(RequestTimeoutError) as exc_info:
        await ChatService().chat(pinned(timeout_ms=2000))

    error = exc_info.value
    assert error.stage == "fallback"
    assert error.model_id == "mock-echo-medium"
    assert error.started is False
    assert error.remaining_ms < 1200
    assert providers.calls == ["mock-echo"]  # medium was never called


# --- Quality evaluation and escalation -----------------------------------------------


async def _slow_judge(self, prompt, response):
    await asyncio.sleep(SLOW)
    return 0.95


async def test_quality_evaluation_respects_remaining_budget(
    temp_registry, temp_db, gateway_env, providers, monkeypatch
):
    set_env(monkeypatch, EVALUATE_ON_CHAT="true")
    monkeypatch.setattr(ChatService, "_evaluate_response_quality", _slow_judge)

    started = time.monotonic()
    with pytest.raises(RequestTimeoutError) as exc_info:
        await ChatService().chat(pinned(timeout_ms=1500))
    wall_ms = (time.monotonic() - started) * 1000

    assert exc_info.value.stage == "evaluation"
    assert exc_info.value.model_id == "mock-echo"
    assert exc_info.value.started is True
    assert wall_ms < 4000


async def test_evaluation_outside_fallback_also_respects_budget(
    temp_registry, temp_db, gateway_env, providers, monkeypatch
):
    """With fallback disabled the executor doesn't judge; ChatService judges the final
    response itself. That call must be bounded too."""
    set_env(monkeypatch, EVALUATE_ON_CHAT="true", FALLBACK_ENABLED="false")
    monkeypatch.setattr(ChatService, "_evaluate_response_quality", _slow_judge)

    with pytest.raises(RequestTimeoutError) as exc_info:
        await ChatService().chat(pinned(timeout_ms=1500))

    assert exc_info.value.stage == "evaluation"
    assert exc_info.value.started is True


async def test_escalation_respects_remaining_budget(
    temp_registry, temp_db, gateway_env, providers, monkeypatch
):
    set_env(monkeypatch, EVALUATE_ON_CHAT="true")

    async def low_for_small(self, prompt, response):
        return 0.40 if response.startswith(SMALL_PREFIX) else 0.93

    monkeypatch.setattr(ChatService, "_evaluate_response_quality", low_for_small)
    providers.delays["mock-echo-medium"] = SLOW

    with pytest.raises(RequestTimeoutError) as exc_info:
        await ChatService().chat(pinned(timeout_ms=1500))

    error = exc_info.value
    assert error.stage == "escalation"
    assert error.model_id == "mock-echo-medium"
    assert error.started is True


async def test_escalation_not_started_when_budget_exhausted(
    temp_registry, temp_db, gateway_env, providers, monkeypatch
):
    # The judge takes 1500ms, leaving at most ~1000ms: below the 1200ms minimum, so the
    # escalation is refused before it starts (tolerates up to ~950ms of overhead).
    set_env(monkeypatch, EVALUATE_ON_CHAT="true", REQUEST_MIN_ATTEMPT_BUDGET_MS="1200")

    async def slow_low_judge(self, prompt, response):
        await asyncio.sleep(1.5)
        return 0.40

    monkeypatch.setattr(ChatService, "_evaluate_response_quality", slow_low_judge)

    with pytest.raises(RequestTimeoutError) as exc_info:
        await ChatService().chat(pinned(timeout_ms=2500))

    error = exc_info.value
    assert error.stage == "escalation"
    assert error.started is False
    assert providers.calls == ["mock-echo"]  # medium was never called


# --- Health interaction --------------------------------------------------------------


async def test_timeout_does_not_count_as_health_failure(temp_registry, temp_db, gateway_env, providers):
    providers.delays["mock-echo"] = SLOW

    for _ in range(5):  # well past the failure threshold of 3
        with pytest.raises(RequestTimeoutError) as exc_info:
            await ChatService().chat(pinned(timeout_ms=300))
        assert exc_info.value.started is True  # the provider call really ran and was cut off

    assert providers.calls == ["mock-echo"] * 5
    snapshot = health.get_model_health("mock-echo", "mock")
    assert snapshot.state == CircuitState.CLOSED
    assert snapshot.consecutive_failures == 0
    assert snapshot.recent_failures == 0
    assert snapshot.recent_successes == 0


async def test_retryable_provider_failure_still_affects_health(temp_registry, temp_db, gateway_env, providers):
    providers.errors["mock-echo"] = ProviderErrorCode.TIMEOUT  # provider-reported, not the deadline

    for _ in range(3):
        response = await ChatService().chat(pinned(timeout_ms=5000))
        assert response.model == "mock-echo-medium"

    snapshot = health.get_model_health("mock-echo", "mock")
    assert snapshot.state == CircuitState.OPEN
    assert snapshot.consecutive_failures == 3


async def test_deadline_during_half_open_trial_releases_the_trial(
    temp_registry, temp_db, gateway_env, providers, monkeypatch
):
    set_env(monkeypatch, HEALTH_COOLDOWN_SECONDS="0.2")
    config = health.get_health_config()
    for _ in range(config.failure_threshold):
        health.record_failure("mock-echo", "mock", "simulated outage", config=config)
    await asyncio.sleep(0.3)  # cooldown elapses; the next attempt becomes the trial

    providers.delays["mock-echo"] = SLOW
    with pytest.raises(RequestTimeoutError) as exc_info:
        await ChatService().chat(pinned(timeout_ms=600))

    assert exc_info.value.started is True
    assert providers.calls == ["mock-echo"]  # the trial did start
    snapshot = health.get_model_health("mock-echo", "mock", config=config)
    assert snapshot.state == CircuitState.OPEN  # not stuck half-open, not closed
    assert snapshot.consecutive_failures == config.failure_threshold  # no failure added
    available, _ = health.check_and_claim_for_generation("mock-echo", "mock", config=config)
    assert available is True  # a new trial can be claimed right away


# --- API surface ---------------------------------------------------------------------


def test_pinned_model_timeout_returns_structured_504(temp_registry, temp_db, gateway_env, providers):
    providers.delays["mock-echo"] = SLOW

    response = client.post(
        "/api/chat",
        json={
            "model": "mock-echo",
            "timeout_ms": 500,
            "request_id": "api-timeout-1",
            "messages": [{"role": "user", "content": PROMPT}],
        },
    )

    assert response.status_code == 504
    assert response.headers["X-Request-ID"] == "api-timeout-1"
    detail = response.json()["detail"]
    assert detail["error"] == "request_timeout"
    assert detail["request_id"] == "api-timeout-1"
    assert detail["stage"] == "generation"
    assert detail["model_id"] == "mock-echo"
    assert detail["timeout_ms"] == 500
    assert detail["elapsed_ms"] >= 450
    assert detail["remaining_ms"] == 0
    assert "500ms" in detail["message"]


def test_openai_compat_timeout_header_and_error(temp_registry, temp_db, gateway_env, providers):
    providers.delays["mock-echo"] = SLOW

    response = client.post(
        "/v1/chat/completions",
        headers={"X-Request-Timeout-Ms": "500", "X-Request-ID": "oa-timeout"},
        json={"model": "mock-echo", "messages": [{"role": "user", "content": PROMPT}]},
    )

    assert response.status_code == 504
    assert response.headers["X-Request-ID"] == "oa-timeout"
    error = response.json()["error"]
    assert error["code"] == "request_timeout"
    assert error["type"] == "server_error"
    assert error["details"]["stage"] == "generation"
    assert error["details"]["request_id"] == "oa-timeout"


def test_timeout_ms_validation(temp_registry, temp_db, gateway_env):
    response = client.post(
        "/api/chat",
        json={"model": "mock-echo", "timeout_ms": 0, "messages": [{"role": "user", "content": PROMPT}]},
    )
    assert response.status_code == 422


# --- Capability + health + timeout together ------------------------------------------


async def test_capability_health_and_timeout_interact(temp_registry, temp_db, gateway_env, providers):
    # small: no tools. medium: tools but circuit open. strong: tools, healthy, slow.
    temp_registry.update_model("mock-echo-medium", ModelUpdateRequest(supports_tools=True))
    temp_registry.update_model("mock-echo-strong", ModelUpdateRequest(supports_tools=True))
    config = health.get_health_config()
    for _ in range(config.failure_threshold):
        health.record_failure("mock-echo-medium", "mock", "simulated outage", config=config)
    providers.delays["mock-echo-strong"] = SLOW

    with pytest.raises(RequestTimeoutError) as exc_info:
        await ChatService().chat(
            ChatRequest(
                model="auto",
                messages=[ChatMessage(role="user", content=PROMPT)],
                tools=[{"type": "function", "function": {"name": "lookup"}}],
                timeout_ms=600,
            )
        )

    error = exc_info.value
    assert error.stage == "generation"
    assert error.started is True
    assert error.model_id == "mock-echo-strong"  # only capable + healthy candidate
    assert providers.calls == ["mock-echo-strong"]
    strong = health.get_model_health("mock-echo-strong", "mock")
    assert strong.consecutive_failures == 0 and strong.recent_failures == 0


async def test_timeout_is_independent_of_max_latency_ms(temp_registry, temp_db, gateway_env, providers):
    """max_latency_ms filters on *average* latency metadata; it doesn't bound execution.
    A model within max_latency_ms can still exceed timeout_ms."""
    providers.delays["mock-echo"] = SLOW  # metadata says 50ms

    with pytest.raises(RequestTimeoutError) as exc_info:
        await ChatService().chat(pinned(max_latency_ms=60, timeout_ms=500))
    assert exc_info.value.stage == "generation"
    assert exc_info.value.started is True


# --- RequestDeadline unit behavior ---------------------------------------------------


async def test_deadline_does_not_start_awaitable_when_exhausted():
    deadline = RequestDeadline.start(50, min_attempt_budget_ms=10, request_id="unit")
    await asyncio.sleep(0.1)
    started = []

    async def work():
        started.append(True)
        return "done"

    with pytest.raises(RequestTimeoutError) as exc_info:
        await deadline.run(work(), "generation", "mock-echo")

    assert started == []
    assert exc_info.value.started is False
    assert exc_info.value.to_dict()["remaining_ms"] == 0
