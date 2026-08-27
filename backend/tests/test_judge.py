"""Tests for judge evaluation."""

import pytest

from app.evaluation.judge import MockJudge


@pytest.mark.asyncio
async def test_mock_judge_evaluate():
    judge = MockJudge()
    score = await judge.evaluate(
        prompt="Explain recursion in Python with an example.",
        response="Recursion is when a function calls itself. Example: def factorial(n)...",
    )
    assert 0.0 <= score.overall <= 1.0
    assert score.judge_provider == "mock"
    assert score.judge_reasoning


@pytest.mark.asyncio
async def test_mock_judge_compare():
    judge = MockJudge()
    result = await judge.compare(
        prompt="Summarize machine learning.",
        response_a="Machine learning learns patterns from data.",
        response_b="Hi",
        label_a="model_a",
        label_b="model_b",
    )
    assert result.winner in {"model_a", "model_b", "tie"}
