"""LLM-as-judge evaluation system."""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod

import httpx

from app.config.settings import Settings, get_settings
from app.providers.base import ProviderError, ProviderErrorCode
from app.schemas.evaluation import JudgeScore, PairwiseJudgeResult


class BaseJudge(ABC):
    @abstractmethod
    async def evaluate(self, prompt: str, response: str) -> JudgeScore:
        """Score a single response against a prompt."""

    @abstractmethod
    async def compare(self, prompt: str, response_a: str, response_b: str, label_a: str, label_b: str) -> PairwiseJudgeResult:
        """Compare two responses pairwise."""


class MockJudge(BaseJudge):
    """Deterministic heuristic judge for local development and tests."""

    async def evaluate(self, prompt: str, response: str) -> JudgeScore:
        prompt_words = {word.lower() for word in re.findall(r"\b\w+\b", prompt) if len(word) > 3}
        response_words = {word.lower() for word in re.findall(r"\b\w+\b", response)}
        overlap = len(prompt_words & response_words)
        relevance = min(1.0, overlap / max(len(prompt_words), 1))
        completeness = min(1.0, len(response.strip()) / 180)
        instruction_following = 0.9 if response.strip() else 0.1
        reasoning_quality = min(1.0, len(response.split(".")) / 4)
        correctness = min(1.0, 0.5 + relevance * 0.5)
        overall = round(
            (correctness + relevance + completeness + instruction_following + reasoning_quality) / 5,
            2,
        )
        return JudgeScore(
            correctness=round(correctness, 2),
            relevance=round(relevance, 2),
            completeness=round(completeness, 2),
            reasoning_quality=round(reasoning_quality, 2),
            instruction_following=round(instruction_following, 2),
            overall=overall,
            judge_provider="mock",
            judge_reasoning="Heuristic scoring based on prompt overlap, response length, and structure.",
        )

    async def compare(self, prompt: str, response_a: str, response_b: str, label_a: str, label_b: str) -> PairwiseJudgeResult:
        score_a = await self.evaluate(prompt, response_a)
        score_b = await self.evaluate(prompt, response_b)
        if score_a.overall > score_b.overall:
            winner = label_a
            confidence = min(0.99, 0.5 + (score_a.overall - score_b.overall))
        elif score_b.overall > score_a.overall:
            winner = label_b
            confidence = min(0.99, 0.5 + (score_b.overall - score_a.overall))
        else:
            winner = "tie"
            confidence = 0.5
        return PairwiseJudgeResult(
            winner=winner,
            confidence=round(confidence, 2),
            reason=f"{label_a} overall={score_a.overall}, {label_b} overall={score_b.overall}",
            judge_provider="mock",
        )


class LLMJudge(BaseJudge):
    """Configurable LLM judge using an OpenAI-compatible chat completion endpoint."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.model_id = self.settings.judge_model_id or "gpt-4o-mini"
        self.timeout = self.settings.provider_timeout

    def _available(self) -> bool:
        return bool(self.settings.openai_api_key)

    async def _call_judge(self, system_prompt: str, user_prompt: str) -> dict:
        if not self._available():
            raise ProviderError(
                "Judge requires OPENAI_API_KEY when JUDGE_PROVIDER=openai.",
                code=ProviderErrorCode.MISSING_API_KEY,
            )
        headers = {
            "Authorization": f"Bearer {self.settings.openai_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model_id,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.0,
            "response_format": {"type": "json_object"},
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=payload,
            )
        if response.status_code >= 400:
            raise ProviderError(
                f"Judge API error ({response.status_code}): {response.text[:300]}",
                code=ProviderErrorCode.PROVIDER_ERROR,
            )
        content = response.json()["choices"][0]["message"]["content"]
        return json.loads(content)

    async def evaluate(self, prompt: str, response: str) -> JudgeScore:
        system_prompt = (
            "You are an evaluation judge. Score the assistant response from 0 to 1 for: "
            "correctness, relevance, completeness, reasoning_quality, instruction_following, overall. "
            "Return strict JSON with numeric fields and a short judge_reasoning string."
        )
        user_prompt = f"Prompt:\n{prompt}\n\nResponse:\n{response}"
        data = await self._call_judge(system_prompt, user_prompt)
        return JudgeScore(
            correctness=float(data.get("correctness", 0)),
            relevance=float(data.get("relevance", 0)),
            completeness=float(data.get("completeness", 0)),
            reasoning_quality=float(data.get("reasoning_quality", 0)),
            instruction_following=float(data.get("instruction_following", 0)),
            overall=float(data.get("overall", 0)),
            judge_provider="openai",
            judge_reasoning=str(data.get("judge_reasoning", "")),
        )

    async def compare(self, prompt: str, response_a: str, response_b: str, label_a: str, label_b: str) -> PairwiseJudgeResult:
        system_prompt = (
            "Compare two assistant responses. Return JSON with winner, confidence (0-1), and reason."
        )
        user_prompt = (
            f"Prompt:\n{prompt}\n\nResponse A ({label_a}):\n{response_a}\n\nResponse B ({label_b}):\n{response_b}"
        )
        data = await self._call_judge(system_prompt, user_prompt)
        return PairwiseJudgeResult(
            winner=str(data.get("winner", "tie")),
            confidence=float(data.get("confidence", 0.5)),
            reason=str(data.get("reason", "")),
            judge_provider="openai",
        )


def get_judge(settings: Settings | None = None) -> BaseJudge:
    settings = settings or get_settings()
    if settings.judge_provider == "openai":
        return LLMJudge(settings)
    return MockJudge()
