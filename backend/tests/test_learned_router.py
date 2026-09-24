"""Learned router: local evidence, cold-start fallback, quality guard, hard filters, collection.

Offline: the dependency-free hashing embedder and mock providers only.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.config.settings import get_settings
from app.db import outcome_repository
from app.models.registry import get_model_registry
from app.router.base import create_router
from app.router.capabilities import NoCapableModelError
from app.router.embedder import embed_prompt, from_bytes, to_bytes
from app.router.features import extract_features
from app.router.learned import LearnedRouter, predict_quality, segment_is_degraded, History
from app.router.task_classifier import classify_task
from app.schemas.models import ModelUpdateRequest
from app.schemas.routing import RouteRequest

CHEAP, MID, STRONG = "mock-echo", "mock-echo-medium", "mock-echo-strong"
PROMPT_A = "Explain how a hash table handles collisions using chaining."
PROMPT_B = "Write a poem about the ocean at night."


def set_env(monkeypatch, **values):
    for key, value in values.items():
        monkeypatch.setenv(key, str(value))
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def learned_env(monkeypatch):
    set_env(
        monkeypatch,
        ROUTER_TYPE="learned",
        EMBEDDING_MODEL="hashing",
        QUALITY_FLOOR="0.80",
        LEARNED_MIN_SAMPLES="5",
        GUARD_MIN_SAMPLES="10",
        EVALUATE_ON_CHAT="false",
        APP_ENV="development",
    )
    registry = get_model_registry()
    for model in registry.list_models():
        registry.set_enabled(model.id, model.provider == "mock")
    prices = {CHEAP: (0.1, 0.4), MID: (1.0, 4.0), STRONG: (5.0, 20.0)}
    for model_id, (cost_in, cost_out) in prices.items():
        registry.update_model(
            model_id, ModelUpdateRequest(input_cost_per_1m_tokens=cost_in, output_cost_per_1m_tokens=cost_out)
        )


def task_of(prompt: str) -> str:
    return classify_task(extract_features(prompt))[0].value


def seed(model_id: str, prompt: str, quality: float, count: int, *, task_type: str | None = None) -> None:
    model = get_model_registry().get_model(model_id)
    blob = to_bytes(embed_prompt(prompt))
    for _ in range(count):
        outcome_id = outcome_repository.record_outcome(
            model_id=model_id,
            provider=model.provider,
            model_tier=model.tier.value,
            stage="generation",
            outcome="success",
            success=True,
            task_type=task_type or task_of(prompt),
            difficulty=0.3,
            embedding=blob,
        )
        outcome_repository.set_quality(outcome_id, quality, quality_failure=False)


def route(prompt: str, **configuration):
    return LearnedRouter().route(RouteRequest(prompt=prompt), configuration or None)


# --- Pure estimate -------------------------------------------------------------------------------


def test_estimate_is_the_prior_without_similar_history():
    vec = embed_prompt(PROMPT_A)
    quality, evidence = predict_quality(0.9, vec, None, k=40, prior_weight=3, min_similarity=0.5)
    assert (quality, evidence) == (0.9, 0.0)
    unrelated = (np.vstack([embed_prompt(PROMPT_B)]), np.array([0.1], dtype=np.float32))
    quality, evidence = predict_quality(0.9, vec, unrelated, k=40, prior_weight=3, min_similarity=0.5)
    assert quality == pytest.approx(0.9) and evidence == 0.0


def test_estimate_moves_towards_similar_history_as_evidence_grows():
    vec = embed_prompt(PROMPT_A)

    def with_n(n: int) -> float:
        samples = (np.vstack([vec] * n), np.full(n, 0.3, dtype=np.float32))
        return predict_quality(0.9, vec, samples, k=40, prior_weight=3, min_similarity=0.5)[0]

    assert 0.3 < with_n(30) < with_n(3) < 0.9


def test_embedding_round_trips_through_bytes():
    vec = embed_prompt(PROMPT_A)
    assert np.allclose(from_bytes(to_bytes(vec)), vec)
    assert vec.shape == (384,) and abs(float(np.linalg.norm(vec)) - 1.0) < 1e-5


# --- Cold start and failure ------------------------------------------------------------------------


def test_cold_start_uses_the_static_fallback():
    decision = route(PROMPT_A)
    assert decision.features["router_type"] == "learned:fallback"
    assert decision.explanation[0].startswith("Fallback routing (static rules)")
    assert "has not learned your traffic yet" in decision.explanation[0]


def test_encoder_failure_falls_back_instead_of_failing(monkeypatch):
    seed(CHEAP, PROMPT_A, 0.9, 10)

    def broken(_prompt):
        raise RuntimeError("encoder down")

    monkeypatch.setattr("app.router.learned.embed_prompt", broken)
    decision = route(PROMPT_A)
    assert decision.features["router_type"] == "learned:fallback"
    assert "unavailable" in decision.features["fallback_reason"]


# --- Learning ---------------------------------------------------------------------------------------


def test_with_enough_data_but_no_local_evidence_it_picks_the_cheapest_model_meeting_the_floor():
    seed(CHEAP, PROMPT_B, 0.95, 10)  # history exists, but not for the prompt being routed
    decision = route(PROMPT_A)
    assert decision.features["router_type"] == "learned"
    assert decision.selected_model == CHEAP
    assert {item.model_id for item in decision.tier_qualities} == {CHEAP, MID, STRONG}  # all candidates scored


def test_a_model_measured_bad_for_one_kind_of_prompt_is_avoided_only_for_that_kind():
    seed(CHEAP, PROMPT_A, 0.30, 25)
    seed(CHEAP, PROMPT_B, 0.95, 25)

    on_a = route(PROMPT_A)
    on_b = route(PROMPT_B)

    assert on_a.selected_model != CHEAP
    assert on_b.selected_model == CHEAP
    assert next(i for i in on_a.tier_qualities if i.model_id == CHEAP).quality_samples > 0


def test_a_cheaper_model_is_chosen_over_a_pricier_one_that_is_no_better():
    seed(CHEAP, PROMPT_A, 0.93, 25)
    seed(STRONG, PROMPT_A, 0.93, 25)
    assert route(PROMPT_A).selected_model == CHEAP


def test_preferred_model_is_still_honoured():
    seed(CHEAP, PROMPT_B, 0.95, 10)
    decision = route(PROMPT_A, preferred_model=STRONG)
    assert decision.selected_model == STRONG and decision.preferred_model_honored is True


def test_hard_filters_apply_to_every_candidate():
    seed(CHEAP, PROMPT_B, 0.95, 10)
    with pytest.raises(NoCapableModelError):
        route(PROMPT_A, required_capabilities={"requires_tools": True})  # no mock model supports tools


def test_an_open_circuit_removes_a_model_from_consideration():
    from app.router import health

    seed(CHEAP, PROMPT_B, 0.95, 10)
    config = health.get_health_config()
    for _ in range(config.failure_threshold):
        health.record_failure(CHEAP, "mock", "simulated outage", config=config)
    assert route(PROMPT_A).selected_model != CHEAP


# --- Quality guard ------------------------------------------------------------------------------------


def test_guard_needs_enough_recent_answers_before_it_acts():
    history = History({}, {"general_qa": (0.2, 3)})
    assert segment_is_degraded("general_qa", history, 0.8, tolerance=0.05, min_samples=10)[0] is False
    history = History({}, {"general_qa": (0.2, 12)})
    assert segment_is_degraded("general_qa", history, 0.8, tolerance=0.05, min_samples=10)[0] is True
    history = History({}, {"general_qa": (0.78, 12)})  # within tolerance of the floor
    assert segment_is_degraded("general_qa", history, 0.8, tolerance=0.05, min_samples=10)[0] is False


def test_a_degraded_segment_stops_being_cost_optimised():
    # Customers recently received poor answers for this kind of task, whichever model wrote them.
    seed(MID, PROMPT_B, 0.90, 10)  # enough history for the learned path
    seed(MID, "unrelated filler", 0.35, 15, task_type=task_of(PROMPT_A))

    decision = route(PROMPT_A)

    assert decision.features["mode"] == "guarded"
    assert decision.features["segment_degraded"] is True
    assert decision.selected_model == STRONG  # highest estimate, not cheapest
    assert any(line.startswith("Quality guard") for line in decision.explanation)
    assert route(PROMPT_B).features["segment_degraded"] is False  # other segments unaffected


# --- Wiring ---------------------------------------------------------------------------------------------


def test_factory_builds_the_learned_router():
    assert isinstance(create_router("learned"), LearnedRouter)


def test_routing_api_serves_the_learned_router():
    from fastapi.testclient import TestClient

    from app.main import app

    response = TestClient(app).post("/api/route", json={"prompt": PROMPT_A})
    assert response.status_code == 200
    assert response.json()["features"]["router_type"] == "learned:fallback"
