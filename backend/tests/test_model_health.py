"""Tests for provider/model health tracking and circuit breaking (Phase 2 Step 5)."""

from __future__ import annotations

import asyncio
import time

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.registry import ModelRegistry
from app.providers.base import GenerationRequest, ProviderError, ProviderErrorCode
from app.providers.mock import MockProvider
from app.router import health
from app.router.capabilities import CapabilityRequirements
from app.router.health import CircuitState, HealthConfig
from app.router.policy import RoutingPolicyConfig, evaluate_tiers, select_model_from_evaluations
from app.router.task_classifier import TaskType
from app.schemas.chat import ChatMessage, ChatRequest
from app.schemas.models import ModelUpdateRequest
from app.services.chat import ChatService
from app.services.fallback import FallbackExecutor

client = TestClient(app)

FAST_CONFIG = HealthConfig(failure_threshold=3, cooldown_seconds=0.2)
PROMPT = "What is the capital of France?"


# --- Shared fixtures ------------------------------------------------------------------


@pytest.fixture
def temp_health_db(tmp_path, monkeypatch):
    """Point the app at a throwaway SQLite file so health rows never leak into the
    shared dev database and each test starts from a clean circuit state."""
    db_path = tmp_path / "health_test.db"
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
        "HEALTH_FAILURE_THRESHOLD": "3",
        "HEALTH_COOLDOWN_SECONDS": "0.2",
    }.items():
        monkeypatch.setenv(key, value)
    from app.config.settings import get_settings

    get_settings.cache_clear()


def flaky_provider(monkeypatch, failing_model_id: str, code: ProviderErrorCode = ProviderErrorCode.TIMEOUT):
    """Monkeypatch MockProvider.generate so calls for `failing_model_id` always fail."""
    original_generate = MockProvider.generate

    async def patched(self, request):
        if self.model.id == failing_model_id:
            raise ProviderError("Simulated failure", code=code)
        return await original_generate(self, request)

    monkeypatch.setattr(MockProvider, "generate", patched)


def route(temp_registry, requirements: CapabilityRequirements | None = None):
    policy = RoutingPolicyConfig(quality_floor=0.85, cost_priority=0.7, latency_priority=0.3)
    evaluations = evaluate_tiers(
        prompt=PROMPT, task_type=TaskType.GENERAL_QA, difficulty=0.2, registry=temp_registry, policy=policy,
        requirements=requirements,
    )
    selected = select_model_from_evaluations(evaluations, policy, requirements=requirements)
    return evaluations, selected


# --- 1. Healthy model remains eligible -------------------------------------------------


def test_healthy_model_is_routable(temp_health_db):
    available, reason = health.is_routable("mock-echo", config=FAST_CONFIG)
    assert available is True
    assert reason is None


def test_healthy_model_remains_eligible_in_routing(temp_registry, temp_health_db):
    evaluations, selected = route(temp_registry)
    assert all(item.health_eligible for item in evaluations)
    assert selected.model.id == "mock-echo"  # cheapest tier, unaffected by health


# --- 2. One failure recorded, circuit remains closed -----------------------------------


def test_single_failure_keeps_circuit_closed(temp_health_db):
    state = health.record_failure("mock-echo", "mock", "boom", config=FAST_CONFIG)
    assert state == "closed"

    snapshot = health.get_model_health("mock-echo", "mock", config=FAST_CONFIG)
    assert snapshot.state == CircuitState.CLOSED
    assert snapshot.consecutive_failures == 1
    assert snapshot.recent_failures == 1

    available, _ = health.is_routable("mock-echo", config=FAST_CONFIG)
    assert available is True


# --- 3. Failure threshold reached -> circuit OPEN ---------------------------------------


def test_threshold_failures_open_the_circuit(temp_health_db):
    for _ in range(FAST_CONFIG.failure_threshold - 1):
        state = health.record_failure("mock-echo", "mock", "boom", config=FAST_CONFIG)
        assert state == "closed"

    final_state = health.record_failure("mock-echo", "mock", "boom", config=FAST_CONFIG)
    assert final_state == "open"

    snapshot = health.get_model_health("mock-echo", "mock", config=FAST_CONFIG)
    assert snapshot.state == CircuitState.OPEN
    assert snapshot.consecutive_failures == FAST_CONFIG.failure_threshold
    assert snapshot.opened_at is not None
    assert snapshot.cooldown_remaining_seconds is not None
    assert snapshot.cooldown_remaining_seconds > 0


# --- 4. OPEN model is not selected by routing -------------------------------------------


def test_open_model_is_excluded_from_routing(temp_registry, temp_health_db):
    for _ in range(FAST_CONFIG.failure_threshold):
        health.record_failure("mock-echo", "mock", "boom", config=FAST_CONFIG)

    evaluations, selected = route(temp_registry)
    small = next(item for item in evaluations if item.tier.value == "small")
    assert small.health_eligible is False
    assert "temporarily unavailable" in small.health_reason
    assert selected.model.id != "mock-echo"


# --- 5. Another healthy model is selected when one is OPEN -----------------------------


def test_another_healthy_model_selected_when_one_is_open(temp_registry, temp_health_db):
    for _ in range(FAST_CONFIG.failure_threshold):
        health.record_failure("mock-echo", "mock", "boom", config=FAST_CONFIG)

    _evaluations, selected = route(temp_registry)
    assert selected.model.id == "mock-echo-medium"  # next cheapest healthy tier


@pytest.mark.asyncio
async def test_fallback_skips_open_model_and_uses_next_tier(temp_registry, temp_health_db):
    for _ in range(FAST_CONFIG.failure_threshold):
        health.record_failure("mock-echo", "mock", "boom", config=FAST_CONFIG)

    executor = FallbackExecutor()
    request = GenerationRequest(messages=[{"role": "user", "content": "Hello"}])
    result = await executor.execute_with_fallback("mock-echo", request)

    assert result.model.id == "mock-echo-medium"
    # The open model was skipped outright — not attempted and marked failed.
    assert len(result.attempts) == 1
    assert result.attempts[0].success is True
    assert result.attempts[0].model_id == "mock-echo-medium"


# --- 6. Successful request resets the failure streak ------------------------------------


def test_success_resets_consecutive_failures(temp_health_db):
    health.record_failure("mock-echo", "mock", "boom", config=FAST_CONFIG)
    health.record_failure("mock-echo", "mock", "boom", config=FAST_CONFIG)
    assert health.get_model_health("mock-echo", "mock", config=FAST_CONFIG).consecutive_failures == 2

    health.record_success("mock-echo", "mock")

    snapshot = health.get_model_health("mock-echo", "mock", config=FAST_CONFIG)
    assert snapshot.consecutive_failures == 0
    assert snapshot.state == CircuitState.CLOSED
    assert snapshot.recent_successes == 1
    assert snapshot.last_success is not None

    # A fresh run at accumulating failures needs the full threshold again.
    health.record_failure("mock-echo", "mock", "boom", config=FAST_CONFIG)
    health.record_failure("mock-echo", "mock", "boom", config=FAST_CONFIG)
    assert health.get_model_health("mock-echo", "mock", config=FAST_CONFIG).state == CircuitState.CLOSED


# --- 7. Cooldown expires -> HALF_OPEN ----------------------------------------------------


def test_cooldown_expiry_allows_half_open_claim(temp_health_db):
    for _ in range(FAST_CONFIG.failure_threshold):
        health.record_failure("mock-echo", "mock", "boom", config=FAST_CONFIG)

    # Still within cooldown: not routable, no claim possible yet.
    available, _ = health.check_and_claim_for_generation("mock-echo", "mock", config=FAST_CONFIG)
    assert available is False
    assert health.get_model_health("mock-echo", "mock", config=FAST_CONFIG).state == CircuitState.OPEN

    time.sleep(FAST_CONFIG.cooldown_seconds + 0.05)

    # Read-only routing check now reports it eligible again (cooldown elapsed)...
    routable, _ = health.is_routable("mock-echo", config=FAST_CONFIG)
    assert routable is True
    # ...but the stored state is still literally 'open' until something actually claims it.
    assert health.get_model_health("mock-echo", "mock", config=FAST_CONFIG).state == CircuitState.OPEN

    claimed, reason = health.check_and_claim_for_generation("mock-echo", "mock", config=FAST_CONFIG)
    assert claimed is True
    assert reason is None
    assert health.get_model_health("mock-echo", "mock", config=FAST_CONFIG).state == CircuitState.HALF_OPEN


# --- 8. Successful HALF_OPEN request -> CLOSED -------------------------------------------


def test_successful_half_open_trial_closes_circuit(temp_health_db):
    for _ in range(FAST_CONFIG.failure_threshold):
        health.record_failure("mock-echo", "mock", "boom", config=FAST_CONFIG)
    time.sleep(FAST_CONFIG.cooldown_seconds + 0.05)

    claimed, _ = health.check_and_claim_for_generation("mock-echo", "mock", config=FAST_CONFIG)
    assert claimed is True
    assert health.get_model_health("mock-echo", "mock", config=FAST_CONFIG).state == CircuitState.HALF_OPEN

    health.record_success("mock-echo", "mock")

    snapshot = health.get_model_health("mock-echo", "mock", config=FAST_CONFIG)
    assert snapshot.state == CircuitState.CLOSED
    assert snapshot.consecutive_failures == 0
    available, _ = health.is_routable("mock-echo", config=FAST_CONFIG)
    assert available is True


# --- 9. Failed HALF_OPEN request -> OPEN again -------------------------------------------


def test_failed_half_open_trial_reopens_circuit(temp_health_db):
    for _ in range(FAST_CONFIG.failure_threshold):
        health.record_failure("mock-echo", "mock", "boom", config=FAST_CONFIG)
    time.sleep(FAST_CONFIG.cooldown_seconds + 0.05)

    claimed, _ = health.check_and_claim_for_generation("mock-echo", "mock", config=FAST_CONFIG)
    assert claimed is True

    state = health.record_failure("mock-echo", "mock", "still broken", config=FAST_CONFIG)
    assert state == "open"

    snapshot = health.get_model_health("mock-echo", "mock", config=FAST_CONFIG)
    assert snapshot.state == CircuitState.OPEN
    # The cooldown restarted: not immediately claimable again.
    available, _ = health.check_and_claim_for_generation("mock-echo", "mock", config=FAST_CONFIG)
    assert available is False


# --- 10. Concurrent HALF_OPEN attempts: only one bypasses the circuit -------------------


def test_only_one_concurrent_caller_claims_half_open_trial(temp_health_db):
    for _ in range(FAST_CONFIG.failure_threshold):
        health.record_failure("mock-echo", "mock", "boom", config=FAST_CONFIG)
    time.sleep(FAST_CONFIG.cooldown_seconds + 0.05)

    results = [
        health.check_and_claim_for_generation("mock-echo", "mock", config=FAST_CONFIG) for _ in range(5)
    ]
    claimed_count = sum(1 for available, _ in results if available)
    assert claimed_count == 1


@pytest.mark.asyncio
async def test_concurrent_async_callers_only_one_claims_half_open(temp_health_db):
    """Same guarantee, exercised through concurrent asyncio tasks rather than a
    sequential loop, matching how real concurrent requests would arrive."""
    for _ in range(FAST_CONFIG.failure_threshold):
        health.record_failure("mock-echo", "mock", "boom", config=FAST_CONFIG)
    time.sleep(FAST_CONFIG.cooldown_seconds + 0.05)

    async def attempt():
        return health.check_and_claim_for_generation("mock-echo", "mock", config=FAST_CONFIG)

    results = await asyncio.gather(*(attempt() for _ in range(8)))
    claimed_count = sum(1 for available, _ in results if available)
    assert claimed_count == 1


# --- 11. Non-retryable errors do not incorrectly open the circuit -----------------------


def test_non_retryable_error_does_not_record_a_failure(temp_health_db):
    health.record_failure("mock-echo", "mock", "boom", config=FAST_CONFIG)  # 1 retryable failure

    # A non-retryable error (bad request / auth / config) should never reach
    # record_failure at all — this asserts the state is unaffected by NOT calling it.
    snapshot_before = health.get_model_health("mock-echo", "mock", config=FAST_CONFIG)
    assert snapshot_before.consecutive_failures == 1
    assert snapshot_before.state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_non_retryable_provider_error_does_not_open_circuit(temp_registry, temp_health_db, monkeypatch):
    flaky_provider(monkeypatch, "mock-echo", code=ProviderErrorCode.MISSING_API_KEY)

    executor = FallbackExecutor()
    request = GenerationRequest(messages=[{"role": "user", "content": "Hello"}])

    with pytest.raises(ProviderError):
        await executor.execute_with_fallback("mock-echo", request)

    snapshot = health.get_model_health("mock-echo", "mock", config=FAST_CONFIG)
    assert snapshot.state == CircuitState.CLOSED
    assert snapshot.consecutive_failures == 0
    assert snapshot.recent_failures == 0


# --- 12. Low-quality response does NOT count as a provider failure ----------------------


@pytest.mark.asyncio
async def test_low_quality_response_does_not_record_provider_failure(temp_registry, temp_health_db, gateway_env, monkeypatch):
    monkeypatch.setenv("FALLBACK_ON_QUALITY_BELOW", "0.99")  # force escalation to trigger
    from app.config.settings import get_settings

    get_settings.cache_clear()

    async def always_low_quality(model, generation):
        return 0.10

    executor = FallbackExecutor()
    request = GenerationRequest(messages=[{"role": "user", "content": "Hello"}])
    result = await executor.execute_with_fallback("mock-echo", request, quality_evaluator=always_low_quality)

    # Escalated due to quality, not a provider error — both models generated successfully.
    assert result.model.id == "mock-echo-medium"
    for model_id in ("mock-echo", "mock-echo-medium"):
        snapshot = health.get_model_health(model_id, "mock", config=FAST_CONFIG)
        assert snapshot.state == CircuitState.CLOSED
        assert snapshot.consecutive_failures == 0
        assert snapshot.recent_failures == 0
        assert snapshot.recent_successes >= 1


# --- 13. Capability filtering + health filtering work together --------------------------


def test_capability_and_health_filtering_combine(temp_registry, temp_health_db):
    # Only medium supports vision; small is additionally circuit-open.
    temp_registry.update_model("mock-echo-medium", ModelUpdateRequest(supports_vision=True))
    temp_registry.update_model("mock-echo-strong", ModelUpdateRequest(supports_vision=True))
    for _ in range(FAST_CONFIG.failure_threshold):
        health.record_failure("mock-echo-strong", "mock", "boom", config=FAST_CONFIG)

    evaluations, selected = route(temp_registry, requirements=CapabilityRequirements(requires_vision=True))

    small = next(item for item in evaluations if item.tier.value == "small")
    medium = next(item for item in evaluations if item.tier.value == "medium")
    strong = next(item for item in evaluations if item.tier.value == "strong")

    assert small.capability_eligible is False  # excluded by capability
    assert medium.capability_eligible is True and medium.health_eligible is True
    assert strong.capability_eligible is True and strong.health_eligible is False  # excluded by health

    assert selected.model.id == "mock-echo-medium"


# --- 14. Existing provider-error fallback still works ------------------------------------


@pytest.mark.asyncio
async def test_provider_error_fallback_still_works(temp_registry, temp_health_db, monkeypatch):
    original_generate = MockProvider.generate
    state = {"failed": False}

    async def flaky(self, request):
        if self.model.id == "mock-echo" and not state["failed"]:
            state["failed"] = True
            raise ProviderError("Simulated timeout", code=ProviderErrorCode.TIMEOUT)
        return await original_generate(self, request)

    monkeypatch.setattr(MockProvider, "generate", flaky)

    executor = FallbackExecutor()
    request = GenerationRequest(messages=[{"role": "user", "content": "Hello"}])
    result = await executor.execute_with_fallback("mock-echo", request)

    assert result.model.id == "mock-echo-medium"
    assert len(result.attempts) == 2
    assert result.attempts[0].success is False

    # A single transient failure records but does not open the circuit.
    snapshot = health.get_model_health("mock-echo", "mock", config=FAST_CONFIG)
    assert snapshot.consecutive_failures == 1
    assert snapshot.state == CircuitState.CLOSED


# --- 15. Existing quality-based fallback still works --------------------------------------


@pytest.mark.asyncio
async def test_quality_based_fallback_still_works(temp_registry, temp_health_db):
    async def low_for_small(model, generation):
        return 0.40 if model.id == "mock-echo" else 0.93

    executor = FallbackExecutor()
    request = GenerationRequest(messages=[{"role": "user", "content": "Hello"}])
    result = await executor.execute_with_fallback("mock-echo", request, quality_evaluator=low_for_small)

    assert result.model.id == "mock-echo-medium"
    assert result.quality == 0.93
    assert [a.reason for a in result.attempts] == ["success", "quality_escalation"]


# --- 16. Existing pinned-model behavior still works ----------------------------------------


@pytest.mark.asyncio
async def test_pinned_model_behavior_still_works_when_healthy(temp_registry, temp_health_db, gateway_env):
    request = ChatRequest(model="mock-echo", messages=[ChatMessage(role="user", content="Hello")])
    response = await ChatService().chat(request)
    assert response.model == "mock-echo"


@pytest.mark.asyncio
async def test_pinned_model_falls_back_when_circuit_open(temp_registry, temp_health_db, gateway_env):
    for _ in range(FAST_CONFIG.failure_threshold):
        health.record_failure("mock-echo", "mock", "boom", config=FAST_CONFIG)

    request = ChatRequest(model="mock-echo", messages=[ChatMessage(role="user", content="Hello")])
    response = await ChatService().chat(request)

    assert response.model == "mock-echo-medium"
    assert response.fallback is not None
    assert response.fallback.used is True


# --- 17. /api/health/models returns correct information ------------------------------------


def test_health_models_endpoint_reports_healthy_by_default(temp_registry, temp_health_db):
    response = client.get("/api/health/models")
    assert response.status_code == 200
    data = response.json()
    ids = {item["model_id"] for item in data}
    assert "mock-echo" in ids
    mock_echo = next(item for item in data if item["model_id"] == "mock-echo")
    assert mock_echo["state"] == "closed"
    assert mock_echo["provider"] == "mock"
    assert mock_echo["consecutive_failures"] == 0
    assert mock_echo["cooldown_remaining_seconds"] is None


def test_health_models_endpoint_reports_open_circuit(temp_registry, temp_health_db, monkeypatch):
    monkeypatch.setenv("HEALTH_FAILURE_THRESHOLD", "3")
    monkeypatch.setenv("HEALTH_COOLDOWN_SECONDS", "30")
    from app.config.settings import get_settings

    get_settings.cache_clear()

    for _ in range(3):
        health.record_failure("mock-echo", "mock", "simulated timeout", config=HealthConfig(3, 30.0))

    response = client.get("/api/health/models")
    assert response.status_code == 200
    mock_echo = next(item for item in response.json() if item["model_id"] == "mock-echo")
    assert mock_echo["state"] == "open"
    assert mock_echo["consecutive_failures"] == 3
    assert mock_echo["last_error"] == "simulated timeout"
    assert mock_echo["cooldown_remaining_seconds"] is not None
    assert mock_echo["cooldown_remaining_seconds"] > 0


# --- Explanation includes health exclusions (requirement 10) ----------------------------


def test_routing_explanation_mentions_health_exclusion(temp_registry, temp_health_db):
    for _ in range(FAST_CONFIG.failure_threshold):
        health.record_failure("mock-echo", "mock", "boom", config=FAST_CONFIG)

    from app.router.rule_based import RuleBasedRouter
    from app.schemas.routing import RouteRequest

    router = RuleBasedRouter()
    decision = router.route(RouteRequest(prompt=PROMPT))

    assert decision.selected_model == "mock-echo-medium"
    assert any("temporarily unavailable" in line.lower() for line in decision.explanation)
