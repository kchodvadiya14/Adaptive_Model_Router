"""Task type classification from extracted prompt features."""

from __future__ import annotations

from enum import Enum

from app.router.features import PromptFeatures


class TaskType(str, Enum):
    GENERAL_QA = "general_qa"
    CODING = "coding"
    DEBUGGING = "debugging"
    MATHEMATICS = "mathematics"
    REASONING = "reasoning"
    SUMMARIZATION = "summarization"
    EXTRACTION = "extraction"
    TRANSLATION = "translation"
    CREATIVE_WRITING = "creative_writing"
    CLASSIFICATION = "classification"
    TECHNICAL_EXPLANATION = "technical_explanation"
    PLANNING = "planning"
    DATA_ANALYSIS = "data_analysis"


TASK_CAPABILITY_MAP: dict[TaskType, list[str]] = {
    TaskType.CODING: ["coding"],
    TaskType.DEBUGGING: ["coding", "reasoning"],
    TaskType.MATHEMATICS: ["reasoning"],
    TaskType.REASONING: ["reasoning"],
    TaskType.SUMMARIZATION: ["summarization"],
    TaskType.EXTRACTION: ["extraction"],
    TaskType.TRANSLATION: ["translation"],
    TaskType.CREATIVE_WRITING: ["creative_writing"],
    TaskType.CLASSIFICATION: ["classification"],
    TaskType.TECHNICAL_EXPLANATION: ["reasoning", "general"],
    TaskType.PLANNING: ["reasoning", "general"],
    TaskType.DATA_ANALYSIS: ["reasoning", "coding"],
    TaskType.GENERAL_QA: ["general"],
}


def classify_task(features: PromptFeatures) -> tuple[TaskType, float]:
    """Return predicted task type and confidence."""
    lower = features.prompt.lower()
    if any(kw in lower for kw in ("debug", "traceback", "fix this code", "bug in")) and features.has_code:
        return TaskType.DEBUGGING, 0.85

    if not features.task_type_scores:
        if features.has_code:
            return TaskType.CODING, 0.55
        if features.has_math:
            return TaskType.MATHEMATICS, 0.55
        if features.reasoning_score >= 0.5:
            return TaskType.REASONING, 0.5
        return TaskType.GENERAL_QA, 0.45

    if features.task_type_scores.get("debugging", 0) >= 0.3 and features.has_code:
        return TaskType.DEBUGGING, min(features.task_type_scores["debugging"] + 0.25, 0.98)

    best_task = max(features.task_type_scores, key=features.task_type_scores.get)
    confidence = features.task_type_scores[best_task]
    return TaskType(best_task), round(min(confidence + 0.2, 0.98), 2)
