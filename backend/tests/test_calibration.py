"""Calibrating registry quality scores against judged model outcomes."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.db import outcome_repository
from app.main import app
from app.models.registry import get_model_registry
from app.router.policy import difficulty_penalty
from app.schemas.models import ModelTier
from app.services.calibration import calibrate

client = TestClient(app)
MODEL = "mock-echo"


def record(model_id: str, quality: float | None, difficulty: float = 0.0, *, success: bool = True) -> None:
    model = get_model_registry().get_model(model_id)
    outcome_repository.record_outcome(
        model_id=model_id,
        provider=model.provider,
        model_tier=model.tier.value,
        stage="generation",
        outcome="success" if success else "retryable_failure",
        success=success,
        difficulty=difficulty,
        quality_score=quality,
    )


def test_blends_measured_quality_with_the_prior():
    prior = get_model_registry().get_model(MODEL).quality_score
    for _ in range(20):
        record(MODEL, 0.50)

    report = calibrate(min_samples=10, prior_weight=20)

    entry = report.models[0]
    assert entry.scored_count == 20 and entry.sufficient_samples
    assert entry.implied_quality_score == 0.5
    assert entry.calibrated_quality_score == pytest.approx((prior * 20 + 0.5 * 20) / 40, abs=1e-4)
    assert get_model_registry().get_model(MODEL).quality_score == prior  # preview changes nothing


def test_difficulty_of_the_traffic_is_adjusted_for():
    tier = get_model_registry().get_model(MODEL).tier
    for _ in range(10):
        record(MODEL, 0.60, difficulty=0.8)

    entry = calibrate(min_samples=5).models[0]

    assert entry.implied_quality_score == pytest.approx(0.60 + difficulty_penalty(tier, 0.8), abs=1e-4)


def test_too_few_samples_leave_the_score_alone():
    for _ in range(3):
        record(MODEL, 0.10)

    entry = calibrate(min_samples=30, apply=True).models[0]

    assert not entry.sufficient_samples and entry.calibrated_quality_score is None
    assert get_model_registry().get_model(MODEL).quality_score == entry.current_quality_score


def test_unscored_and_failed_attempts_are_ignored():
    record(MODEL, None)
    record(MODEL, 0.2, success=False)

    assert calibrate(min_samples=1).models == []


def test_apply_writes_to_the_registry():
    for _ in range(40):
        record(MODEL, 0.30)

    report = calibrate(min_samples=10, apply=True)

    assert report.applied
    assert get_model_registry().get_model(MODEL).quality_score == report.models[0].calibrated_quality_score
    assert report.models[0].calibrated_quality_score < report.models[0].current_quality_score


def test_api_preview_and_apply():
    for _ in range(12):
        record(MODEL, 0.40)

    preview = client.get("/api/performance/calibration", params={"min_samples": 10})
    assert preview.status_code == 200 and preview.json()["applied"] is False
    before = get_model_registry().get_model(MODEL).quality_score

    applied = client.post("/api/performance/calibration/apply", params={"min_samples": 10})
    assert applied.status_code == 200 and applied.json()["applied"] is True
    assert get_model_registry().get_model(MODEL).quality_score < before
    assert isinstance(get_model_registry().get_model(MODEL).tier, ModelTier)
