"""Tests proving each chat response is judged exactly once across fallback and logging."""

from collections.abc import Callable

import pytest

from app.models.registry import ModelRegistry
from app.providers.base import GenerationRequest, ProviderError, ProviderErrorCode
from app.providers.mock import MockProvider
from app.schemas.chat import ChatMessage, ChatRequest
from app.schemas.evaluation import JudgeScore
from app.services.chat import ChatService
from app.services.fallback import FallbackExecutor

SMALL_PREFIX = "[Mock Mock Echo (Local)]"
MEDIUM_PREFIX = "[Mock Mock Echo Medium (Local)]"

# Low enough that the rule-based router picks the small tier, leaving room to escalate.
ROUTE_TO_SMALL_FLOOR = 0.5


class CountingJudge:
    """Records every response it scores; returns the score chosen by ``score_for``."""

    def __init__(self, score_for: Callable[[str], float]) -> None:
        self.score_for = score_for
        self.calls: list[str] = []

    async def evaluate(self, prompt: str, response: str) -> JudgeScore:
        self.calls.append(response)
        overall = self.score_for(response)
        return JudgeScore(
            correctness=overall,
            relevance=overall,
            completeness=overall,
            reasoning_quality=overall,
            instruction_following=overall,
            overall=overall,
            judge_provider="counting",
        )


@pytest.fixture
def temp_registry(tmp_path, monkeypatch):
    registry = ModelRegistry(registry_path=tmp_path / "model_registry.json")
    monkeypatch.setattr("app.models.registry._registry", registry)
    monkeypatch.setattr("app.services.fallback.get_model_registry", lambda: registry)
    monkeypatch.setattr("app.services.chat.get_model_registry", lambda: registry)
    monkeypatch.setattr("app.router.rule_based.get_model_registry", lambda: registry)
    monkeypatch.setattr("app.router.policy.get_model_registry", lambda: registry)
    return registry


@pytest.fixture
def gateway_env(monkeypatch):
    """Pin the settings these tests depend on, regardless of any local .env."""
    for key, value in {
        "APP_ENV": "development",
        "EVALUATE_ON_CHAT": "true",
        "JUDGE_PROVIDER": "mock",
        "FALLBACK_ENABLED": "true",
        "FALLBACK_ON_QUALITY_BELOW": "0.85",
        "FALLBACK_ESCALATION": "tier_up",
        "MAX_FALLBACK_ATTEMPTS": "3",
        "ROUTER_TYPE": "rule_based",
    }.items():
        monkeypatch.setenv(key, value)
    from app.config.settings import get_settings

    get_settings.cache_clear()


@pytest.fixture
def logged_events(monkeypatch):
    events: list[dict] = []
    monkeypatch.setattr("app.services.chat.log_routing_event", lambda **kwargs: events.append(kwargs) or 1)
    return events


def install_judge(monkeypatch, score_for: Callable[[str], float]) -> CountingJudge:
    judge = CountingJudge(score_for)
    monkeypatch.setattr("app.services.chat.get_judge", lambda *args, **kwargs: judge)
    return judge


def auto_request(content: str = "Explain recursion briefly") -> ChatRequest:
    return ChatRequest(
        model="auto",
        messages=[ChatMessage(role="user", content=content)],
        quality_floor=ROUTE_TO_SMALL_FLOOR,
    )


def low_for_small(response: str) -> float:
    return 0.40 if response.startswith(SMALL_PREFIX) else 0.93


async def test_auto_request_without_escalation_judges_once(temp_registry, gateway_env, logged_events, monkeypatch):
    judge = install_judge(monkeypatch, lambda response: 0.95)

    response = await ChatService().chat(auto_request())

    assert response.model == "mock-echo"
    assert response.fallback is None
    assert len(judge.calls) == 1
    assert judge.calls[0] == response.content
    assert logged_events[0]["actual_quality"] == 0.95


async def test_low_quality_escalation_does_not_rejudge_first_response(
    temp_registry, gateway_env, logged_events, monkeypatch
):
    judge = install_judge(monkeypatch, low_for_small)

    response = await ChatService().chat(auto_request())

    assert response.model == "mock-echo-medium"
    # One score for the rejected small response, one for the escalated response — never the same one twice.
    assert len(judge.calls) == 2
    assert len(set(judge.calls)) == 2
    assert sum(1 for call in judge.calls if call.startswith(SMALL_PREFIX)) == 1


async def test_escalated_response_quality_is_the_one_recorded(temp_registry, gateway_env, logged_events, monkeypatch):
    judge = install_judge(monkeypatch, low_for_small)

    response = await ChatService().chat(auto_request())

    assert response.content.startswith(MEDIUM_PREFIX)
    assert judge.calls[-1] == response.content
    assert logged_events[0]["selected_model"] == "mock-echo-medium"
    assert logged_events[0]["actual_quality"] == 0.93
    assert response.fallback is not None
    assert response.fallback.escalation_reason == "quality_below_threshold"
    assert [attempt.reason for attempt in response.fallback.attempts] == ["success", "quality_escalation"]


async def test_failed_escalation_reuses_original_score(temp_registry, gateway_env, logged_events, monkeypatch):
    judge = install_judge(monkeypatch, low_for_small)
    original_generate = MockProvider.generate

    async def medium_down(self, request):
        if self.model.id == "mock-echo-medium":
            raise ProviderError("Simulated outage", code=ProviderErrorCode.NETWORK_ERROR)
        return await original_generate(self, request)

    monkeypatch.setattr(MockProvider, "generate", medium_down)

    response = await ChatService().chat(auto_request())

    assert response.model == "mock-echo"
    assert len(judge.calls) == 1
    assert logged_events[0]["actual_quality"] == 0.40
    assert response.fallback.attempts[-1].reason == "quality_escalation_failed:network_error"


async def test_provider_error_fallback_still_works_and_judges_once(
    temp_registry, gateway_env, logged_events, monkeypatch
):
    judge = install_judge(monkeypatch, lambda response: 0.95)
    original_generate = MockProvider.generate

    async def small_times_out(self, request):
        if self.model.id == "mock-echo":
            raise ProviderError("Simulated timeout", code=ProviderErrorCode.TIMEOUT)
        return await original_generate(self, request)

    monkeypatch.setattr(MockProvider, "generate", small_times_out)

    response = await ChatService().chat(auto_request())

    assert response.model == "mock-echo-medium"
    assert response.fallback.escalation_reason == "provider_error"
    assert [attempt.success for attempt in response.fallback.attempts] == [False, True]
    assert len(judge.calls) == 1
    assert judge.calls[0] == response.content
    assert logged_events[0]["actual_quality"] == 0.95


async def test_non_retryable_provider_error_still_raises_without_judging(
    temp_registry, gateway_env, logged_events, monkeypatch
):
    judge = install_judge(monkeypatch, lambda response: 0.95)

    async def missing_key(self, request):
        raise ProviderError("No key", code=ProviderErrorCode.MISSING_API_KEY)

    monkeypatch.setattr(MockProvider, "generate", missing_key)

    with pytest.raises(ProviderError) as exc_info:
        await ChatService().chat(auto_request())

    assert exc_info.value.code == ProviderErrorCode.MISSING_API_KEY
    assert judge.calls == []
    assert logged_events == []


async def test_pinned_model_is_judged_once(temp_registry, gateway_env, logged_events, monkeypatch):
    judge = install_judge(monkeypatch, lambda response: 0.95)

    request = ChatRequest(model="mock-echo", messages=[ChatMessage(role="user", content="Hello")])
    response = await ChatService().chat(request)

    assert response.model == "mock-echo"
    assert len(judge.calls) == 1
    assert logged_events[0]["actual_quality"] == 0.95


async def test_executor_reports_unevaluated_when_no_evaluator(temp_registry, gateway_env):
    executor = FallbackExecutor(registry=temp_registry)
    request = GenerationRequest(messages=[{"role": "user", "content": "Hello"}])

    result = await executor.execute_with_fallback("mock-echo", request)

    assert result.model.id == "mock-echo"
    assert result.quality_evaluated is False
    assert result.quality is None
