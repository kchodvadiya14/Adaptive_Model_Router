"""Mock provider for local development and automated tests."""

import asyncio
import time

from app.config.settings import get_settings
from app.providers.base import BaseModelProvider, GenerationRequest, GenerationResponse
from app.utils.tokens import estimate_messages_tokens, estimate_tokens


_ELABORATIONS = (
    "First, the question is restated and its main constraints are identified.",
    "Then the answer is worked through step by step, checking each intermediate result.",
    "Finally, edge cases and common mistakes are noted, with a short summary of the conclusion.",
)
_DETAIL = {"small": 0, "medium": 1, "strong": 3}


class MockProvider(BaseModelProvider):
    """Returns deterministic echo responses without external API calls."""

    provider_name = "mock"

    def is_available(self) -> bool:
        settings = get_settings()
        return settings.app_env in {"development", "test"} or settings.use_mock_providers

    async def generate(self, request: GenerationRequest) -> GenerationResponse:
        start = time.perf_counter()
        await asyncio.sleep(0.05)

        user_messages = [m["content"] for m in request.messages if m["role"] == "user"]
        last_user = user_messages[-1] if user_messages else ""
        content = (
            f"[Mock {self.model.name}] Response to: {last_user[:500]}"
            if last_user
            else f"[Mock {self.model.name}] Hello from the mock provider."
        )
        # Stronger tiers give fuller answers, so a demo's judged quality differs by model the way it
        # would with real ones. Purely simulated: it says nothing about real model quality.
        for extra in _ELABORATIONS[: _DETAIL.get(self.model.tier.value, 0)]:
            content += " " + extra

        input_tokens = estimate_messages_tokens(request.messages)
        output_tokens = estimate_tokens(content)
        latency_ms = (time.perf_counter() - start) * 1000

        return GenerationResponse(
            content=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            finish_reason="stop",
        )
