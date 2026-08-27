"""Tests for rule-based router."""

import pytest

from app.models.registry import ModelRegistry
from app.router.policy import estimate_quality_for_model, get_policy_config
from app.router.rule_based import RuleBasedRouter
from app.router.task_classifier import TaskType
from app.schemas.models import ModelTier
from app.schemas.routing import RouteRequest


@pytest.fixture
def temp_registry(tmp_path, monkeypatch):
    registry_path = tmp_path / "model_registry.json"
    registry = ModelRegistry(registry_path=registry_path)
    monkeypatch.setattr("app.models.registry._registry", registry)
    monkeypatch.setattr("app.router.rule_based.get_model_registry", lambda: registry)
    monkeypatch.setattr("app.router.policy.get_model_registry", lambda: registry)
    return registry


def test_route_simple_prompt_meets_quality_floor(temp_registry):
    router = RuleBasedRouter()
    decision = router.route(RouteRequest(prompt="What is the capital of France?"))
    assert decision.task_type == "general_qa"
    assert decision.difficulty < 0.5
    assert decision.estimated_quality >= get_policy_config().quality_floor
    assert decision.model_tier in {"small", "medium"}
    assert len(decision.explanation) >= 3


def test_route_complex_debugging_to_strong_tier(temp_registry, monkeypatch):
    monkeypatch.setenv("QUALITY_FLOOR", "0.90")
    from app.config.settings import get_settings

    get_settings.cache_clear()

    router = RuleBasedRouter()
    prompt = (
        "Debug this Python code step by step. Analyze the traceback, explain why recursion fails, "
        "and provide a fixed implementation with tests.\n```python\ndef fib(n):\n    return fib(n-1)\n```"
    )
    decision = router.route(RouteRequest(prompt=prompt))
    assert decision.task_type in {"debugging", "coding"}
    assert decision.difficulty >= 0.6
    assert decision.model_tier in {"medium", "strong"}
    assert "Code detected: Yes" in decision.explanation

    get_settings.cache_clear()


def test_route_respects_quality_floor_override(temp_registry):
    router = RuleBasedRouter()
    decision = router.route(
        RouteRequest(prompt="Explain quantum computing in detail with pros and cons."),
        configuration={"quality_floor": 0.95},
    )
    assert decision.estimated_quality >= 0.95


def test_estimate_quality_penalizes_small_model_on_hard_tasks(temp_registry):
    small = temp_registry.get_primary_model_for_tier(ModelTier.SMALL)
    strong = temp_registry.get_primary_model_for_tier(ModelTier.STRONG)
    assert small and strong
    small_q = estimate_quality_for_model(small, TaskType.DEBUGGING, difficulty=0.85)
    strong_q = estimate_quality_for_model(strong, TaskType.DEBUGGING, difficulty=0.85)
    assert strong_q > small_q
