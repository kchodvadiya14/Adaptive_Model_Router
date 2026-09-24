"""Routing learns from judged outcomes: measured quality corrects the hand-set prior."""

from __future__ import annotations

import pytest

from app.db import outcome_repository
from app.models.registry import get_model_registry
from app.router.feedback import TaskQuality, blend_quality
from app.router.rule_based import RuleBasedRouter
from app.schemas.models import ModelTier
from app.schemas.routing import RouteRequest

PROMPT = "Write a Python function that reverses a linked list."


@pytest.fixture(autouse=True)
def floor(monkeypatch):
    from app.config.settings import get_settings

    monkeypatch.setenv("QUALITY_FLOOR", "0.80")
    get_settings.cache_clear()


def seed(model_id: str, task_type: str, quality: float, count: int, difficulty: float) -> None:
    model = get_model_registry().get_model(model_id)
    for _ in range(count):
        outcome_id = outcome_repository.record_outcome(
            model_id=model_id,
            provider=model.provider,
            model_tier=model.tier.value,
            stage="generation",
            outcome="success",
            success=True,
            task_type=task_type,
            difficulty=difficulty,
        )
        outcome_repository.set_quality(outcome_id, quality, quality_failure=False)


def tier_estimate(decision, tier: str):
    return next(item for item in decision.tier_qualities if item.tier == tier)


def test_blend_returns_the_prior_without_enough_evidence():
    observed = TaskQuality(scored_count=3, mean_quality=0.1, mean_difficulty=0.5)
    assert blend_quality(0.85, ModelTier.SMALL, 0.5, observed) == (0.85, 0)
    assert blend_quality(0.85, ModelTier.SMALL, 0.5, None) == (0.85, 0)


def test_blend_moves_towards_measurements_as_samples_grow():
    few = blend_quality(0.85, ModelTier.SMALL, 0.5, TaskQuality(10, 0.40, 0.5))
    many = blend_quality(0.85, ModelTier.SMALL, 0.5, TaskQuality(200, 0.40, 0.5))
    assert 0.40 < many[0] < few[0] < 0.85
    assert few[1] == 10 and many[1] == 200


def test_blend_adjusts_for_the_difficulty_it_was_measured_at():
    hard_then_easy_now = blend_quality(0.85, ModelTier.SMALL, 0.1, TaskQuality(500, 0.60, 0.9))
    same_difficulty = blend_quality(0.85, ModelTier.SMALL, 0.9, TaskQuality(500, 0.60, 0.9))
    assert hard_then_easy_now[0] > same_difficulty[0]


def test_a_fresh_deployment_routes_on_the_prior():
    decision = RuleBasedRouter().route(RouteRequest(prompt=PROMPT))
    assert all(item.quality_samples == 0 for item in decision.tier_qualities)
    assert any("assumed, no judged outcomes yet" in line for line in decision.explanation)


def test_a_model_measured_as_bad_at_a_task_stops_being_chosen_for_it():
    baseline = RuleBasedRouter().route(RouteRequest(prompt=PROMPT))
    chosen = get_model_registry().get_model(baseline.selected_model)

    seed(chosen.id, baseline.task_type, quality=0.35, count=40, difficulty=baseline.difficulty)
    after = RuleBasedRouter().route(RouteRequest(prompt=PROMPT))

    assert after.model_tier != baseline.model_tier
    measured = tier_estimate(after, chosen.tier.value)
    assert measured.quality_samples == 40
    assert measured.expected_quality < tier_estimate(baseline, chosen.tier.value).expected_quality
    assert any("measured on 40 judged" in line for line in after.explanation)


def test_evidence_about_one_task_does_not_leak_into_another():
    baseline = RuleBasedRouter().route(RouteRequest(prompt=PROMPT))
    seed(baseline.selected_model, "translation", quality=0.1, count=40, difficulty=0.3)

    after = RuleBasedRouter().route(RouteRequest(prompt=PROMPT))

    assert after.model_tier == baseline.model_tier
    assert all(item.quality_samples == 0 for item in after.tier_qualities)
