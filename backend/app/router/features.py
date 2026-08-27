"""Prompt feature extraction for routing decisions."""

from __future__ import annotations

import re
from dataclasses import dataclass

CODE_PATTERNS = [
    r"```",
    r"\bdef\s+\w+",
    r"\bclass\s+\w+",
    r"\bimport\s+\w+",
    r"\bfunction\s*\(",
    r"\bconsole\.log\b",
    r"\bprint\s*\(",
    r"\bTraceback\b",
    r"\bError:",
    r"\bbug\b",
    r"\bdebug\b",
]

MATH_PATTERNS = [
    r"\b\d+\s*[\+\-\*/\^=]\s*\d+",
    r"\bintegral\b",
    r"\bderivative\b",
    r"\bequation\b",
    r"\bcalculate\b",
    r"\bsolve\b",
    r"[∑∫√π≤≥≠]",
    r"\$\$.*?\$\$",
    r"\\frac\{",
]

REASONING_PATTERNS = [
    r"\bwhy\b",
    r"\bexplain\b",
    r"\banalyze\b",
    r"\bcompare\b",
    r"\bevaluate\b",
    r"\bprove\b",
    r"\bdeduce\b",
    r"\breasoning\b",
    r"\bstep by step\b",
    r"\bthink through\b",
]

OUTPUT_FORMAT_PATTERNS = {
    "json": r"\bjson\b",
    "table": r"\btable\b",
    "bullet_list": r"\bbullet\b|\blist\b",
    "code": r"\bcode\b|\bscript\b",
    "summary": r"\bsummary\b|\bsummarize\b",
}

TASK_KEYWORDS: dict[str, list[str]] = {
    "coding": ["write code", "implement", "function", "algorithm", "python script", "javascript", "api endpoint"],
    "debugging": ["debug", "fix this", "error", "traceback", "not working", "bug in", "issue with code"],
    "mathematics": ["calculate", "equation", "integral", "derivative", "algebra", "probability", "theorem"],
    "reasoning": ["why", "explain why", "analyze", "compare and contrast", "evaluate", "pros and cons"],
    "summarization": ["summarize", "summary", "tl;dr", "condense", "brief overview"],
    "extraction": ["extract", "find all", "pull out", "parse", "get the", "list the"],
    "translation": ["translate", "in spanish", "in french", "in hindi", "convert to"],
    "creative_writing": ["write a story", "poem", "creative", "narrative", "fiction"],
    "classification": ["classify", "categorize", "label", "which category", "is this"],
    "technical_explanation": ["how does", "explain how", "architecture", "works internally", "under the hood"],
    "planning": ["plan", "roadmap", "strategy", "schedule", "milestones", "project plan"],
    "data_analysis": ["analyze data", "dataset", "csv", "statistics", "correlation", "visualization"],
}


@dataclass
class PromptFeatures:
    prompt: str
    prompt_length: int
    word_count: int
    sentence_count: int
    question_count: int
    instruction_count: int
    has_code: bool
    has_math: bool
    reasoning_score: float
    question_complexity: float
    requested_output_format: str | None
    task_type_scores: dict[str, float]


def _count_matches(text: str, patterns: list[str]) -> int:
    return sum(1 for pattern in patterns if re.search(pattern, text, re.IGNORECASE))


def _count_instructions(text: str) -> int:
    numbered = len(re.findall(r"(?m)^\s*\d+[\.\)]\s+", text))
    bullets = len(re.findall(r"(?m)^\s*[-*]\s+", text))
    imperatives = len(re.findall(r"\b(list|describe|write|create|implement|fix|compare|analyze)\b", text, re.I))
    return numbered + bullets + min(imperatives, 5)


def extract_features(prompt: str) -> PromptFeatures:
    """Extract structured features from a user prompt."""
    text = prompt.strip()
    lower = text.lower()
    words = re.findall(r"\b\w+\b", lower)
    sentences = [s for s in re.split(r"[.!?]+", text) if s.strip()]

    has_code = any(re.search(p, text, re.IGNORECASE) for p in CODE_PATTERNS)
    has_math = any(re.search(p, text, re.IGNORECASE) for p in MATH_PATTERNS)
    reasoning_hits = _count_matches(lower, REASONING_PATTERNS)
    reasoning_score = min(1.0, reasoning_hits / 4.0)

    wh_questions = len(re.findall(r"\b(what|why|how|when|where|which|who)\b", lower))
    question_count = text.count("?")
    question_complexity = min(1.0, (question_count + wh_questions) / 5.0)

    output_format = None
    for fmt, pattern in OUTPUT_FORMAT_PATTERNS.items():
        if re.search(pattern, lower):
            output_format = fmt
            break

    task_scores: dict[str, float] = {}
    for task_type, keywords in TASK_KEYWORDS.items():
        hits = sum(1 for kw in keywords if kw in lower)
        if hits:
            task_scores[task_type] = min(1.0, hits / max(len(keywords) * 0.3, 1))

    if has_code and "debugging" not in task_scores:
        task_scores.setdefault("coding", 0.6)
    if has_math:
        task_scores["mathematics"] = max(task_scores.get("mathematics", 0.0), 0.7)

    return PromptFeatures(
        prompt=text,
        prompt_length=len(text),
        word_count=len(words),
        sentence_count=max(len(sentences), 1),
        question_count=question_count,
        instruction_count=_count_instructions(text),
        has_code=has_code,
        has_math=has_math,
        reasoning_score=reasoning_score,
        question_complexity=question_complexity,
        requested_output_format=output_format,
        task_type_scores=task_scores,
    )
