"""Tests for quality-based escalation on requests that pin a specific model.

Step 1 (test_judge_dedup.py) proved each response is judged at most once and that
score is reused for logging. This file proves the same quality-escalation path that
already worked for model="auto" now also applies when a caller pins a model directly.
"""

from collections.abc import Callable

import pytest

from app.models.registry import ModelRegistry
from app.providers.base import ProviderError, ProviderErrorCode
from app.providers.mock import MockProvider
from app.schemas.chat import ChatMessage, ChatRequest
from app.schemas.evaluation import JudgeScore
from app.services.chat import ChatService

SMALL_PREFIX = "[Mock Mock Echo (Local)]"
MEDIUM_PREFIX = "[Mock Mock Echo Medium (Local)]"
STRONG_PREFIX = "[Mock Mock Echo Strong (Local)]"


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


def pinned_request(model: str, content: str = "Explain recursion briefly") -> ChatRequest:
    return ChatRequest(model=model, messages=[ChatMessage(role="user", content=content)])


def low_only_for(prefix: str) -> Callable[[str], float]:
    return lambda response: 0.40 if response.startswith(prefix) else 0.93


async def test_pinned_small_model_low_quality_escalates_to_medium(temp_registry, gateway_env, logged_events, monkeypatch):
    judge = install_judge(monkeypatch, low_only_for(SMALL_PREFIX))

    response = await ChatService().chat(pinned_request("mock-echo"))

    assert response.model == "mock-echo-medium"
    assert response.content.startswith(MEDIUM_PREFIX)
    assert len(judge.calls) == 2
    assert len(set(judge.calls)) == 2  # no response scored twice
    assert response.fallback is not None
    assert response.fallback.original_model == "mock-echo"
    assert response.fallback.final_model == "mock-echo-medium"
    assert response.fallback.escalation_reason == "quality_below_threshold"
    assert [a.reason for a in response.fallback.attempts] == ["success", "quality_escalation"]
    assert logged_events[0]["selected_model"] == "mock-echo-medium"
    assert logged_events[0]["actual_quality"] == 0.93


async def test_pinned_medium_model_low_quality_escalates_to_strong(temp_registry, gateway_env, logged_events, monkeypatch):
    judge = install_judge(monkeypatch, low_only_for(MEDIUM_PREFIX))

    response = await ChatService().chat(pinned_request("mock-echo-medium"))

    assert response.model == "mock-echo-strong"
    assert response.content.startswith(STRONG_PREFIX)
    assert len(judge.calls) == 2
    assert response.fallback.escalation_reason == "quality_below_threshold"
    assert logged_events[0]["selected_model"] == "mock-echo-strong"
    assert logged_events[0]["actual_quality"] == 0.93


async def test_pinned_strong_model_low_quality_does_not_escalate_further(
    temp_registry, gateway_env, logged_events, monkeypatch
):
    judge = install_judge(monkeypatch, lambda response: 0.40)

    response = await ChatService().chat(pinned_request("mock-echo-strong"))

    assert response.model == "mock-echo-strong"
    assert response.content.startswith(STRONG_PREFIX)
    # Already the strongest tier: scored once, nowhere left to escalate to.
    assert len(judge.calls) == 1
    assert response.fallback is None
    assert logged_events[0]["selected_model"] == "mock-echo-strong"
    assert logged_events[0]["actual_quality"] == 0.40


async def test_pinned_model_acceptable_quality_does_not_escalate(temp_registry, gateway_env, logged_events, monkeypatch):
    judge = install_judge(monkeypatch, lambda response: 0.93)

    response = await ChatService().chat(pinned_request("mock-echo"))

    assert response.model == "mock-echo"
    assert len(judge.calls) == 1
    assert response.fallback is None
    assert logged_events[0]["actual_quality"] == 0.93


async def test_pinned_model_provider_error_still_falls_back(temp_registry, gateway_env, logged_events, monkeypatch):
    judge = install_judge(monkeypatch, lambda response: 0.93)
    original_generate = MockProvider.generate

    async def small_times_out(self, request):
        if self.model.id == "mock-echo":
            raise ProviderError("Simulated timeout", code=ProviderErrorCode.TIMEOUT)
        return await original_generate(self, request)

    monkeypatch.setattr(MockProvider, "generate", small_times_out)

    response = await ChatService().chat(pinned_request("mock-echo"))

    assert response.model == "mock-echo-medium"
    assert response.fallback.escalation_reason == "provider_error"
    assert [a.success for a in response.fallback.attempts] == [False, True]
    # Only the response actually returned is judged.
    assert len(judge.calls) == 1
    assert judge.calls[0] == response.content


async def test_provider_error_then_low_quality_continues_to_next_tier(
    temp_registry, gateway_env, logged_events, monkeypatch
):
    judge = install_judge(monkeypatch, low_only_for(MEDIUM_PREFIX))
    original_generate = MockProvider.generate

    async def small_times_out(self, request):
        if self.model.id == "mock-echo":
            raise ProviderError("Simulated timeout", code=ProviderErrorCode.TIMEOUT)
        return await original_generate(self, request)

    monkeypatch.setattr(MockProvider, "generate", small_times_out)

    response = await ChatService().chat(pinned_request("mock-echo"))

    # small -> provider error -> medium (succeeds, but scored low) -> strong (quality escalation)
    assert response.model == "mock-echo-strong"
    assert [a.reason for a in response.fallback.attempts] == [
        "timeout",
        "success",
        "quality_escalation",
    ]
    assert len(judge.calls) == 2
    assert logged_events[0]["actual_quality"] == 0.93


async def test_fallback_disabled_skips_escalation_but_still_logs_quality(
    temp_registry, gateway_env, logged_events, monkeypatch
):
    monkeypatch.setenv("FALLBACK_ENABLED", "false")
    from app.config.settings import get_settings

    get_settings.cache_clear()

    judge = install_judge(monkeypatch, lambda response: 0.10)

    response = await ChatService().chat(pinned_request("mock-echo"))

    assert response.model == "mock-echo"
    assert response.fallback is None
    # Still judged once for logging/metrics, just never consulted for escalation.
    assert len(judge.calls) == 1
    assert logged_events[0]["actual_quality"] == 0.10
