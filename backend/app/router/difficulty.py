"""Difficulty estimation for incoming prompts."""

from __future__ import annotations

from app.router.features import PromptFeatures
from app.router.task_classifier import TaskType


TASK_BASE_DIFFICULTY: dict[TaskType, float] = {
    TaskType.GENERAL_QA: 0.25,
    TaskType.CODING: 0.55,
    TaskType.DEBUGGING: 0.70,
    TaskType.MATHEMATICS: 0.65,
    TaskType.REASONING: 0.60,
    TaskType.SUMMARIZATION: 0.30,
    TaskType.EXTRACTION: 0.35,
    TaskType.TRANSLATION: 0.30,
    TaskType.CREATIVE_WRITING: 0.40,
    TaskType.CLASSIFICATION: 0.25,
    TaskType.TECHNICAL_EXPLANATION: 0.50,
    TaskType.PLANNING: 0.55,
    TaskType.DATA_ANALYSIS: 0.60,
}


def difficulty_label(score: float) -> str:
    if score < 0.3:
        return "easy"
    if score < 0.7:
        return "medium"
    return "hard"


def estimate_difficulty(features: PromptFeatures, task_type: TaskType) -> float:
    """Estimate prompt difficulty on a 0–1 scale."""
    base = TASK_BASE_DIFFICULTY.get(task_type, 0.35)

    length_factor = min(1.0, features.word_count / 400) * 0.15
    instruction_factor = min(1.0, features.instruction_count / 6) * 0.15
    reasoning_factor = features.reasoning_score * 0.15
    question_factor = features.question_complexity * 0.1
    code_factor = 0.12 if features.has_code else 0.0
    math_factor = 0.10 if features.has_math else 0.0

    score = base + length_factor + instruction_factor + reasoning_factor + question_factor + code_factor + math_factor
    return round(min(max(score, 0.0), 1.0), 2)
