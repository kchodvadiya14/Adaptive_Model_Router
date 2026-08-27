"""OpenAI provider adapter."""

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


class OpenAIProvider(BaseModelProvider):
    provider_name = "openai"

    def __init__(self, model) -> None:
        super().__init__(model)
        self.settings = get_settings()
        self.base_url = "https://api.openai.com/v1"
        self.timeout = self.settings.provider_timeout

    def is_available(self) -> bool:
        return bool(self.settings.openai_api_key)

    async def generate(self, request: GenerationRequest) -> GenerationResponse:
        if not self.is_available():
            raise ProviderError(
                "OpenAI API key is not configured. Set OPENAI_API_KEY in your environment.",
                code=ProviderErrorCode.MISSING_API_KEY,
            )

        start = time.perf_counter()
        payload = {
            "model": self.model.id,
            "messages": request.messages,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }
        headers = {
            "Authorization": f"Bearer {self.settings.openai_api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                )
        except httpx.TimeoutException as exc:
            raise ProviderError(
                "OpenAI request timed out.",
                code=ProviderErrorCode.TIMEOUT,
            ) from exc
        except httpx.RequestError as exc:
            raise ProviderError(
                f"Network error contacting OpenAI: {exc}",
                code=ProviderErrorCode.NETWORK_ERROR,
            ) from exc

        if response.status_code == 429:
            raise ProviderError(
                "OpenAI rate limit exceeded.",
                code=ProviderErrorCode.RATE_LIMIT,
                status_code=429,
            )

        if response.status_code >= 400:
            detail = response.text[:300]
            raise ProviderError(
                f"OpenAI API error ({response.status_code}): {detail}",
                code=ProviderErrorCode.PROVIDER_ERROR,
                status_code=response.status_code,
            )

        data = response.json()
        try:
            content = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})
            input_tokens = usage.get("prompt_tokens", estimate_messages_tokens(request.messages))
            output_tokens = usage.get("completion_tokens", estimate_tokens(content))
            finish_reason = data["choices"][0].get("finish_reason")
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(
                "Invalid response format from OpenAI.",
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
