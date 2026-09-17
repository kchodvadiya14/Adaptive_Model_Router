"""Tests for capability-aware routing: hard eligibility filtering before cost/quality."""

import pytest

from app.models.registry import ModelRegistry
from app.router.capabilities import (
    CapabilityRequirements,
    NoCapableModelError,
    model_meets_capabilities,
)
from app.router.policy import (
    RoutingPolicyConfig,
    evaluate_tiers,
    select_model_from_evaluations,
)
from app.router.task_classifier import TaskType
from app.schemas.chat import ChatMessage, ChatRequest
from app.schemas.models import ModelUpdateRequest
from app.services.chat import ChatService

PROMPT = "What is the capital of France?"


@pytest.fixture
def temp_registry(tmp_path, monkeypatch):
    registry = ModelRegistry(registry_path=tmp_path / "model_registry.json")
    monkeypatch.setattr("app.models.registry._registry", registry)
    monkeypatch.setattr("app.router.rule_based.get_model_registry", lambda: registry)
    monkeypatch.setattr("app.router.policy.get_model_registry", lambda: registry)
    monkeypatch.setattr("app.services.chat.get_model_registry", lambda: registry)
    return registry


@pytest.fixture
def gateway_env(monkeypatch):
    for key, value in {
        "APP_ENV": "development",
        "EVALUATE_ON_CHAT": "false",  # isolate routing from judge/fallback for these tests
        "ROUTER_TYPE": "rule_based",
        "QUALITY_FLOOR": "0.85",
    }.items():
        monkeypatch.setenv(key, value)
    from app.config.settings import get_settings

    get_settings.cache_clear()


def route(temp_registry, requirements: CapabilityRequirements | None = None):
    policy = RoutingPolicyConfig(quality_floor=0.85, cost_priority=0.7, latency_priority=0.3)
    evaluations = evaluate_tiers(
        prompt=PROMPT,
        task_type=TaskType.GENERAL_QA,
        difficulty=0.2,
        registry=temp_registry,
        policy=policy,
        requirements=requirements,
    )
    selected = select_model_from_evaluations(evaluations, policy, requirements=requirements)
    return evaluations, selected


# --- 1. Normal text request: unchanged behavior -----------------------------------------


def test_text_request_without_requirements_behaves_as_before(temp_registry):
    evaluations, selected = route(temp_registry, requirements=None)

    assert selected.model is not None
    assert all(item.capability_eligible for item in evaluations)
    # No capability requirement was given, so the small (cheapest) tier still wins on cost.
    assert selected.tier.value == "small"


def test_text_request_with_inactive_requirements_matches_no_requirements(temp_registry):
    """CapabilityRequirements() with everything False/0 must be a no-op filter."""
    _, selected_a = route(temp_registry, requirements=None)
    _, selected_b = route(temp_registry, requirements=CapabilityRequirements())

    assert selected_a.model.id == selected_b.model.id


# --- 2. Vision request: models without vision support are excluded ----------------------


def test_vision_request_excludes_models_without_vision_support(temp_registry):
    temp_registry.update_model("mock-echo-strong", ModelUpdateRequest(supports_vision=True))
    # small/medium keep the default supports_vision=False.

    evaluations, selected = route(temp_registry, requirements=CapabilityRequirements(requires_vision=True))

    small = next(item for item in evaluations if item.tier.value == "small")
    medium = next(item for item in evaluations if item.tier.value == "medium")
    strong = next(item for item in evaluations if item.tier.value == "strong")

    assert small.capability_eligible is False
    assert "vision" in small.capability_reason
    assert medium.capability_eligible is False
    assert strong.capability_eligible is True
    assert selected.model.id == "mock-echo-strong"


# --- 3. Tool-calling request: models without tool support are excluded ------------------


def test_tool_request_excludes_models_without_tool_support(temp_registry):
    temp_registry.update_model("mock-echo-medium", ModelUpdateRequest(supports_tools=True))
    temp_registry.update_model("mock-echo-strong", ModelUpdateRequest(supports_tools=True))

    evaluations, selected = route(temp_registry, requirements=CapabilityRequirements(requires_tools=True))

    small = next(item for item in evaluations if item.tier.value == "small")
    assert small.capability_eligible is False
    assert "tool" in small.capability_reason
    # Cheapest capable tier (medium) wins, not the more expensive strong tier.
    assert selected.model.id == "mock-echo-medium"


# --- 4. Large-context request: models whose context_window is too small are excluded ----


def test_large_context_request_excludes_small_context_models(temp_registry):
    temp_registry.update_model("mock-echo", ModelUpdateRequest(context_window=4000))
    temp_registry.update_model("mock-echo-medium", ModelUpdateRequest(context_window=8000))
    temp_registry.update_model("mock-echo-strong", ModelUpdateRequest(context_window=64000))

    evaluations, selected = route(temp_registry, requirements=CapabilityRequirements(min_context_tokens=20000))

    small = next(item for item in evaluations if item.tier.value == "small")
    medium = next(item for item in evaluations if item.tier.value == "medium")
    strong = next(item for item in evaluations if item.tier.value == "strong")

    assert small.capability_eligible is False
    assert "context window" in small.capability_reason
    assert medium.capability_eligible is False
    assert strong.capability_eligible is True
    assert selected.model.id == "mock-echo-strong"


# --- 5. Only one model/tier supports the required capability ----------------------------


def test_only_one_capable_tier_is_selected_even_if_more_expensive(temp_registry):
    # Strong tier is normally the most expensive/least cost-preferred; capability
    # filtering must still pick it because it is the *only* eligible option.
    temp_registry.update_model("mock-echo-strong", ModelUpdateRequest(supports_tools=True))

    evaluations, selected = route(temp_registry, requirements=CapabilityRequirements(requires_tools=True))

    capable_tiers = [item.tier.value for item in evaluations if item.capability_eligible]
    assert capable_tiers == ["strong"]
    assert selected.model.id == "mock-echo-strong"


# --- 6. No model supports the capability: clear structured error ------------------------


def test_no_capable_model_raises_structured_error(temp_registry):
    # None of the mock models support vision by default.
    with pytest.raises(NoCapableModelError) as exc_info:
        route(temp_registry, requirements=CapabilityRequirements(requires_vision=True))

    error = exc_info.value
    assert error.requirements.requires_vision is True
    assert len(error.excluded) == 3
    assert all("vision" in item.reason for item in error.excluded)
    assert "vision" in str(error)


def test_no_capable_model_error_is_a_value_error(temp_registry):
    # Preserves the pre-existing ValueError-based error contract used by /api/route.
    with pytest.raises(ValueError):
        route(temp_registry, requirements=CapabilityRequirements(requires_vision=True))


# --- 7. Capability filtering happens BEFORE cost/quality comparison ---------------------


def test_capability_filtering_precedes_cost_comparison(temp_registry):
    """Small is cheapest and meets the quality floor, but only medium has vision.
    If capability were a soft score bump instead of a hard filter, small could still win."""
    temp_registry.update_model("mock-echo-medium", ModelUpdateRequest(supports_vision=True))

    evaluations, selected = route(temp_registry, requirements=CapabilityRequirements(requires_vision=True))

    small = next(item for item in evaluations if item.tier.value == "small")
    assert small.meets_quality_floor is True  # would have won on cost/quality alone
    assert small.capability_eligible is False  # but is hard-excluded regardless
    assert selected.model.id == "mock-echo-medium"


def test_capability_ineligible_tier_never_wins_even_with_higher_quality(temp_registry):
    """A capability-ineligible tier must never be selected, even if we make it look
    like the best cost/quality/latency choice — proves the filter runs first, not as
    a tiebreaker."""
    temp_registry.update_model(
        "mock-echo",
        ModelUpdateRequest(quality_score=0.99, avg_latency_ms=1, input_cost_per_1m_tokens=0.0),
    )
    temp_registry.update_model("mock-echo-medium", ModelUpdateRequest(supports_tools=True))

    evaluations, selected = route(temp_registry, requirements=CapabilityRequirements(requires_tools=True))

    small = next(item for item in evaluations if item.tier.value == "small")
    assert small.expected_quality >= 0.9  # objectively the "best" tier by every soft metric
    assert small.capability_eligible is False
    assert selected.model.id == "mock-echo-medium"


def test_explanation_mentions_capability_exclusion(temp_registry):
    temp_registry.update_model("mock-echo-strong", ModelUpdateRequest(supports_tools=True))

    from app.router.rule_based import RuleBasedRouter
    from app.schemas.routing import RouteRequest

    router = RuleBasedRouter()
    decision = router.route(
        RouteRequest(prompt=PROMPT),
        configuration={"required_capabilities": {"requires_tools": True}},
    )

    assert decision.selected_model == "mock-echo-strong"
    assert any("excluded" in line.lower() for line in decision.explanation)
    assert any("tool" in line.lower() for line in decision.explanation)


# --- model_meets_capabilities unit checks ------------------------------------------------


def test_model_meets_capabilities_no_requirements_is_always_eligible(temp_registry):
    model = temp_registry.get_model("mock-echo")
    eligible, reason = model_meets_capabilities(model, None)
    assert eligible is True
    assert reason is None


# --- 8/9. Existing auto-routing and pinned-model/fallback behavior is untouched ---------


async def test_auto_chat_request_without_special_requirements_is_unaffected(temp_registry, gateway_env):
    request = ChatRequest(model="auto", messages=[ChatMessage(role="user", content=PROMPT)])
    response = await ChatService().chat(request)

    assert response.routed is True
    assert response.model == "mock-echo"  # cheapest tier, exactly as before this step


async def test_pinned_model_request_is_not_capability_filtered(temp_registry, gateway_env):
    """Capability requirements are only used to choose a model for model='auto'; a
    pinned model request is unaffected by this step (unchanged from Step 1/2)."""
    request = ChatRequest(
        model="mock-echo",
        messages=[ChatMessage(role="user", content=PROMPT, has_image=True)],
    )
    response = await ChatService().chat(request)

    assert response.model == "mock-echo"


async def test_vision_chat_request_routes_to_vision_capable_model(temp_registry, gateway_env):
    temp_registry.update_model("mock-echo-strong", ModelUpdateRequest(supports_vision=True))

    request = ChatRequest(
        model="auto",
        messages=[ChatMessage(role="user", content="Describe this image", has_image=True)],
    )
    response = await ChatService().chat(request)

    assert response.model == "mock-echo-strong"
    assert response.routing is not None
    assert response.routing.selected_model == "mock-echo-strong"


async def test_tool_chat_request_routes_to_tool_capable_model(temp_registry, gateway_env):
    temp_registry.update_model("mock-echo-medium", ModelUpdateRequest(supports_tools=True))

    request = ChatRequest(
        model="auto",
        messages=[ChatMessage(role="user", content="Look up the weather for me")],
        tools=[{"type": "function", "function": {"name": "get_weather"}}],
    )
    response = await ChatService().chat(request)

    assert response.model == "mock-echo-medium"
