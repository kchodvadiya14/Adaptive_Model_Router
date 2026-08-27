"""Tests for difficulty estimation and task classification."""

from app.router.difficulty import difficulty_label, estimate_difficulty
from app.router.features import extract_features
from app.router.task_classifier import TaskType, classify_task


def test_classify_coding_task():
    features = extract_features("Write a Python function to implement binary search.")
    task_type, confidence = classify_task(features)
    assert task_type == TaskType.CODING
    assert confidence > 0.4


def test_difficulty_increases_for_debugging():
    easy = extract_features("What is Python?")
    hard = extract_features(
        "Debug this complex Python traceback with multiple steps, analyze why recursion fails, and fix the bug."
    )
    easy_task, _ = classify_task(easy)
    hard_task, _ = classify_task(hard)
    easy_score = estimate_difficulty(easy, easy_task)
    hard_score = estimate_difficulty(hard, hard_task)
    assert hard_score > easy_score


def test_difficulty_labels():
    assert difficulty_label(0.2) == "easy"
    assert difficulty_label(0.5) == "medium"
    assert difficulty_label(0.8) == "hard"
