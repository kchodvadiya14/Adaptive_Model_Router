"""Anthropic provider adapter."""

import time

import httpx

from app.config.settings import get_settings
from app.providers.base import (
    BaseModelProvider,
    GenerationRequest,
    GenerationResponse,
    ProviderError,
    ProviderErrorCode,
)
from app.utils.tokens import estimate_messages_tokens, estimate_tokens


class AnthropicProvider(BaseModelProvider):
    provider_name = "anthropic"

    def __init__(self, model) -> None:
        super().__init__(model)
        self.settings = get_settings()
        self.base_url = "https://api.anthropic.com/v1"
        self.timeout = self.settings.provider_timeout

    def is_available(self) -> bool:
        return bool(self.settings.anthropic_api_key)

    def _split_messages(self, messages: list[dict[str, str]]) -> tuple[str | None, list[dict[str, str]]]:
        system_prompt: str | None = None
        converted: list[dict[str, str]] = []
        for message in messages:
            if message["role"] == "system":
                system_prompt = message["content"]
            else:
                converted.append({"role": message["role"], "content": message["content"]})
        if not converted:
            converted = [{"role": "user", "content": "Hello"}]
        return system_prompt, converted

    async def generate(self, request: GenerationRequest) -> GenerationResponse:
        if not self.is_available():
            raise ProviderError(
                "Anthropic API key is not configured. Set ANTHROPIC_API_KEY in your environment.",
                code=ProviderErrorCode.MISSING_API_KEY,
            )

        start = time.perf_counter()
        system_prompt, messages = self._split_messages(request.messages)
        payload: dict = {
            "model": self.model.id,
            "messages": messages,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }
        if system_prompt:
            payload["system"] = system_prompt

        headers = {
            "x-api-key": self.settings.anthropic_api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/messages",
                    headers=headers,
                    json=payload,
                )
        except httpx.TimeoutException as exc:
            raise ProviderError("Anthropic request timed out.", code=ProviderErrorCode.TIMEOUT) from exc
        except httpx.RequestError as exc:
            raise ProviderError(
                f"Network error contacting Anthropic: {exc}",
                code=ProviderErrorCode.NETWORK_ERROR,
            ) from exc

        if response.status_code == 429:
            raise ProviderError(
                "Anthropic rate limit exceeded.",
                code=ProviderErrorCode.RATE_LIMIT,
                status_code=429,
            )

        if response.status_code >= 400:
            detail = response.text[:300]
            raise ProviderError(
                f"Anthropic API error ({response.status_code}): {detail}",
                code=ProviderErrorCode.PROVIDER_ERROR,
                status_code=response.status_code,
            )

        data = response.json()
        try:
            content_blocks = data.get("content", [])
            content = "".join(block.get("text", "") for block in content_blocks if block.get("type") == "text")
            usage = data.get("usage", {})
            input_tokens = usage.get("input_tokens", estimate_messages_tokens(request.messages))
            output_tokens = usage.get("output_tokens", estimate_tokens(content))
            finish_reason = data.get("stop_reason")
        except (KeyError, TypeError) as exc:
            raise ProviderError(
                "Invalid response format from Anthropic.",
                code=ProviderErrorCode.INVALID_RESPONSE,
            ) from exc

        latency_ms = (time.perf_counter() - start) * 1000
        return GenerationResponse(
            content=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            finish_reason=finish_reason,
        )
