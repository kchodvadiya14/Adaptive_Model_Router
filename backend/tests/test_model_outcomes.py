"""Tests for per-attempt model outcome recording and historical performance reporting
(Phase 3 Step 9). Offline: mock providers with scripted behavior; judge stubbed or off.
Database and registry are isolated per test by tests/conftest.py."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.db import outcome_repository
from app.main import app
from app.models.registry import get_model_registry
from app.providers.base import ProviderError, ProviderErrorCode
from app.providers.mock import MockProvider
from app.router import health
from app.router.health import CircuitState
from app.router.policy import RoutingPolicyConfig, evaluate_tiers, select_model_from_evaluations
from app.router.task_classifier import TaskType
from app.schemas.chat import ChatMessage, ChatRequest
from app.schemas.models import ModelUpdateRequest
from app.schemas.performance import PerformanceFilters
from app.services.chat import ChatService
from app.services.deadline import RequestTimeoutError
from app.services.performance import get_model_performance

client = TestClient(app)

PROMPT = "What is the capital of France?"
SMALL_PREFIX = "[Mock Mock Echo (Local)]"


# --- Fixtures -----------------------------------------------------------------------


def set_env(monkeypatch, **values):
    for key, value in values.items():
        monkeypatch.setenv(key, str(value))
    from app.config.settings import get_settings

    get_settings.cache_clear()


@pytest.fixture(autouse=True)
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
        QUALITY_FLOOR="0.90",
    )


class ProviderScript:
    def __init__(self, monkeypatch):
        self.delays: dict[str, float] = {}
        self.errors: dict[str, ProviderErrorCode] = {}
        original_generate = MockProvider.generate
        script = self

        async def scripted(provider_self, request):
            model_id = provider_self.model.id
            await asyncio.sleep(script.delays.get(model_id, 0.0))
            if model_id in script.errors:
                code = script.errors[model_id]
                raise ProviderError(f"Simulated {code.value}", code=code)
            return await original_generate(provider_self, request)

        monkeypatch.setattr(MockProvider, "generate", scripted)


@pytest.fixture
def providers(monkeypatch):
    return ProviderScript(monkeypatch)


def chat_request(**overrides) -> ChatRequest:
    fields = {"model": "mock-echo", "messages": [ChatMessage(role="user", content=PROMPT)]}
    fields.update(overrides)
    return ChatRequest(**fields)


def outcomes_for(request_id: str) -> list[dict]:
    return outcome_repository.list_outcomes(request_id=request_id)


def judge(monkeypatch, score_for):
    set_env(monkeypatch, EVALUATE_ON_CHAT="true")

    async def stub(self, prompt, response):
        return score_for(response)

    monkeypatch.setattr(ChatService, "_evaluate_response_quality", stub)


# --- Recording: successful generation ------------------------------------------------


async def test_successful_routed_generation_is_recorded():
    response = await ChatService().chat(chat_request(model="auto", request_id="ok-1"))

    rows = outcomes_for("ok-1")
    assert len(rows) == 1
    row = rows[0]
    assert row["model_id"] == response.model
    assert row["provider"] == "mock"
    assert row["model_tier"] == response.tier
    assert row["task_type"] == response.routing.task_type == "general_qa"
    assert row["difficulty"] == response.routing.difficulty
    assert row["stage"] == "generation"
    assert row["outcome"] == "success"
    assert row["success"] == 1
    assert row["error_code"] is None
    assert row["latency_ms"] > 0
    assert row["quality_score"] is None  # judge disabled
    assert row["fallback_used"] == 0
    assert datetime.fromisoformat(row["timestamp"]).tzinfo is not None


async def test_estimated_cost_matches_token_based_cost():
    get_model_registry().update_model(
        "mock-echo", ModelUpdateRequest(input_cost_per_1m_tokens=3.0, output_cost_per_1m_tokens=15.0)
    )

    response = await ChatService().chat(chat_request(request_id="cost-1"))

    row = outcomes_for("cost-1")[0]
    assert response.cost.total_cost > 0
    assert row["estimated_cost"] == pytest.approx(response.cost.total_cost)
    assert row["task_type"] is None and row["difficulty"] is None  # pinned: not routed


# --- Recording: provider failures and fallback ---------------------------------------


async def test_retryable_failure_and_fallback_attempt_are_both_recorded(providers):
    providers.errors["mock-echo"] = ProviderErrorCode.RATE_LIMIT

    response = await ChatService().chat(chat_request(request_id="fb-1"))

    assert response.model == "mock-echo-medium"
    failed, recovered = outcomes_for("fb-1")
    assert failed["model_id"] == "mock-echo"
    assert failed["stage"] == "generation"
    assert failed["outcome"] == "retryable_failure"
    assert failed["success"] == 0
    assert failed["error_code"] == "rate_limit"
    assert failed["latency_ms"] is not None
    assert failed["estimated_cost"] is None  # no tokens came back, so no cost is claimed
    assert failed["fallback_used"] == 1
    assert recovered["model_id"] == "mock-echo-medium"
    assert recovered["stage"] == "fallback"
    assert recovered["outcome"] == "success"
    assert recovered["fallback_used"] == 0


async def test_non_retryable_failure_is_recorded_separately(providers):
    providers.errors["mock-echo"] = ProviderErrorCode.MISSING_API_KEY

    with pytest.raises(ProviderError):
        await ChatService().chat(chat_request(request_id="nr-1"))

    rows = outcomes_for("nr-1")
    assert len(rows) == 1  # non-retryable: no fallback attempt followed
    assert rows[0]["outcome"] == "non_retryable_failure"
    assert rows[0]["error_code"] == "missing_api_key"
    assert rows[0]["fallback_used"] == 0
    assert health.get_model_health("mock-echo", "mock").consecutive_failures == 0


async def test_models_refused_before_a_provider_call_are_not_recorded():
    config = health.get_health_config()
    for _ in range(config.failure_threshold):
        health.record_failure("mock-echo", "mock", "simulated outage", config=config)

    response = await ChatService().chat(chat_request(request_id="skip-1"))

    assert response.model == "mock-echo-medium"
    assert [row["model_id"] for row in outcomes_for("skip-1")] == ["mock-echo-medium"]


# --- Recording: timeout --------------------------------------------------------------


async def test_timeout_is_recorded_without_becoming_a_provider_failure(providers):
    providers.delays["mock-echo"] = 5.0

    with pytest.raises(RequestTimeoutError):
        await ChatService().chat(chat_request(request_id="to-1", timeout_ms=300))

    rows = outcomes_for("to-1")
    assert len(rows) == 1
    assert rows[0]["outcome"] == "timeout"
    assert rows[0]["success"] == 0
    assert rows[0]["error_code"] == "request_timeout"
    # Measured around the provider call only; timeout_ms also covers routing before it.
    assert 0 < rows[0]["latency_ms"] <= 300
    snapshot = health.get_model_health("mock-echo", "mock")
    assert snapshot.consecutive_failures == 0 and snapshot.recent_failures == 0


# --- Recording: quality ---------------------------------------------------------------


async def test_quality_escalation_is_recorded(monkeypatch):
    judge(monkeypatch, lambda response: 0.40 if response.startswith(SMALL_PREFIX) else 0.93)

    response = await ChatService().chat(chat_request(request_id="q-1"))

    assert response.model == "mock-echo-medium"
    low, escalated = outcomes_for("q-1")
    assert low["model_id"] == "mock-echo"
    assert low["outcome"] == "quality_failure"
    assert low["success"] == 1  # the model answered; the answer was just not good enough
    assert low["quality_score"] == pytest.approx(0.40)
    assert low["fallback_used"] == 1
    assert escalated["model_id"] == "mock-echo-medium"
    assert escalated["stage"] == "escalation"
    assert escalated["outcome"] == "success"
    assert escalated["quality_score"] == pytest.approx(0.93)
    assert escalated["fallback_used"] == 0


async def test_quality_failure_without_escalation_target_is_still_recorded(monkeypatch):
    judge(monkeypatch, lambda response: 0.40)

    response = await ChatService().chat(chat_request(model="mock-echo-strong", request_id="q-2"))

    assert response.model == "mock-echo-strong"
    (row,) = outcomes_for("q-2")
    assert row["outcome"] == "quality_failure"
    assert row["fallback_used"] == 0  # nowhere to escalate to


async def test_quality_score_attached_when_judged_outside_the_executor(monkeypatch):
    judge(monkeypatch, lambda response: 0.40)
    set_env(monkeypatch, FALLBACK_ENABLED="false")

    await ChatService().chat(chat_request(request_id="q-3"))

    (row,) = outcomes_for("q-3")
    assert row["quality_score"] == pytest.approx(0.40)
    assert row["outcome"] == "success"  # no escalation threshold applies without fallback


async def test_recording_failure_never_breaks_a_request(monkeypatch):
    def broken(**kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr(outcome_repository, "record_outcome", broken)

    response = await ChatService().chat(chat_request(request_id="broken-1"))

    assert response.model == "mock-echo"


# --- Aggregation ---------------------------------------------------------------------


def _seed(model_id="mock-echo", *, outcome="success", latency_ms=100.0, cost=None, quality=None,
          fallback=False, task_type="general_qa", at=None, provider="mock"):
    outcome_id = outcome_repository.record_outcome(
        model_id=model_id,
        provider=provider,
        stage="generation",
        outcome=outcome,
        success=outcome in ("success", "quality_failure"),
        task_type=task_type,
        latency_ms=latency_ms,
        estimated_cost=cost,
        quality_score=quality,
        recorded_at=at,
    )
    if fallback:
        outcome_repository.mark_fallback_used(outcome_id)
    return outcome_id


def test_aggregation_correctness():
    _seed(outcome="success", latency_ms=100, cost=0.001, quality=0.9)
    _seed(outcome="success", latency_ms=300, cost=0.003, quality=0.7)
    _seed(outcome="quality_failure", latency_ms=200, cost=0.002, quality=0.4, fallback=True)
    _seed(outcome="retryable_failure", latency_ms=50, fallback=True)
    _seed(outcome="timeout", latency_ms=500)
    _seed("mock-echo-medium", outcome="success", latency_ms=80, cost=0.01, quality=1.0)

    report = get_model_performance(PerformanceFilters())

    assert [model.model_id for model in report.models] == ["mock-echo", "mock-echo-medium"]
    small = report.models[0]
    assert small.provider == "mock"
    assert small.request_count == 5
    assert small.success_count == 3
    assert small.success_rate == pytest.approx(0.6)
    assert small.quality_failure_rate == pytest.approx(0.2)
    assert small.fallback_rate == pytest.approx(0.4)
    assert small.average_latency_ms == pytest.approx(200.0)  # successful attempts only
    assert small.average_estimated_cost == pytest.approx(0.002)
    assert small.average_quality_score == pytest.approx(0.6667, abs=1e-4)
    assert small.outcomes.model_dump() == {
        "success": 2,
        "quality_failure": 1,
        "retryable_failure": 1,
        "non_retryable_failure": 0,
        "timeout": 1,
    }


def test_model_with_no_successes_reports_none_averages():
    _seed(outcome="retryable_failure", latency_ms=50)

    (model,) = get_model_performance(PerformanceFilters()).models
    assert model.success_rate == 0.0
    assert model.average_latency_ms is None
    assert model.average_estimated_cost is None
    assert model.average_quality_score is None


# --- Filtering (service + API) --------------------------------------------------------


def test_filter_by_model_and_task_type():
    _seed("mock-echo", task_type="coding")
    _seed("mock-echo", task_type="general_qa")
    _seed("mock-echo-medium", task_type="coding")
    _seed("mock-echo-medium", task_type=None)  # pinned request: no task type

    by_model = client.get("/api/performance/models", params={"model_id": "mock-echo"}).json()
    assert [m["model_id"] for m in by_model["models"]] == ["mock-echo"]
    assert by_model["models"][0]["request_count"] == 2

    by_task = client.get("/api/performance/models", params={"task_type": "coding"}).json()
    assert {m["model_id"]: m["request_count"] for m in by_task["models"]} == {"mock-echo": 1, "mock-echo-medium": 1}

    both = client.get("/api/performance/models", params={"model_id": "mock-echo-medium", "task_type": "coding"}).json()
    assert both["models"][0]["request_count"] == 1
    assert both["filters"] == {"model_id": "mock-echo-medium", "task_type": "coding", "since": None, "until": None}

    none = client.get("/api/performance/models", params={"model_id": "no-such-model"}).json()
    assert none["models"] == []


def test_filter_by_time_window():
    now = datetime.now(UTC)
    _seed(at=now - timedelta(days=3), latency_ms=900)
    _seed(at=now - timedelta(hours=2), latency_ms=100)
    _seed(at=now - timedelta(minutes=5), latency_ms=300)

    last_day = client.get(
        "/api/performance/models", params={"since": (now - timedelta(days=1)).isoformat()}
    ).json()["models"][0]
    assert last_day["request_count"] == 2
    assert last_day["average_latency_ms"] == pytest.approx(200.0)

    window = client.get(
        "/api/performance/models",
        params={"since": (now - timedelta(days=4)).isoformat(), "until": (now - timedelta(hours=1)).isoformat()},
    ).json()["models"][0]
    assert window["request_count"] == 2
    assert window["average_latency_ms"] == pytest.approx(500.0)


def test_naive_datetimes_are_treated_as_utc():
    now = datetime.now(UTC)
    _seed(at=now - timedelta(hours=2))
    naive_since = (now - timedelta(hours=1)).replace(tzinfo=None).isoformat()

    data = client.get("/api/performance/models", params={"since": naive_since}).json()
    assert data["models"] == []


def test_since_after_until_is_rejected():
    now = datetime.now(UTC)
    response = client.get(
        "/api/performance/models",
        params={"since": now.isoformat(), "until": (now - timedelta(hours=1)).isoformat()},
    )
    assert response.status_code == 422


# --- Existing behavior preserved -------------------------------------------------------


async def test_existing_health_behavior_is_unchanged(providers):
    providers.errors["mock-echo"] = ProviderErrorCode.TIMEOUT

    for attempt in range(3):
        await ChatService().chat(chat_request(request_id=f"h-{attempt}"))

    assert health.get_model_health("mock-echo", "mock").state == CircuitState.OPEN
    small = get_model_performance(PerformanceFilters(model_id="mock-echo")).models[0]
    assert small.outcomes.retryable_failure == 3


async def test_existing_usage_behavior_is_unchanged(providers):
    providers.errors["mock-echo"] = ProviderErrorCode.NETWORK_ERROR

    await ChatService().chat(chat_request(request_id="u-1", user_id="alice"))

    usage = client.get("/api/usage", params={"user_id": "alice"}).json()
    assert usage["total_requests"] == 1  # still one routing-log row per request
    assert usage["fallback_requests"] == 1
    assert len(outcomes_for("u-1")) == 2  # while feedback has one row per attempt


def test_history_does_not_change_routing_decisions():
    policy = RoutingPolicyConfig(quality_floor=0.85, cost_priority=0.7, latency_priority=0.3)

    def selected() -> str:
        evaluations = evaluate_tiers(PROMPT, TaskType.GENERAL_QA, 0.2, policy=policy)
        return select_model_from_evaluations(evaluations, policy).model.id

    before = selected()
    for _ in range(50):  # terrible history for the model routing would pick
        _seed(before, outcome="retryable_failure", latency_ms=10_000)
    assert selected() == before
