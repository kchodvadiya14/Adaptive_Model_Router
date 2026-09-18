"""Google Gemini provider adapter."""

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


class GoogleProvider(BaseModelProvider):
    provider_name = "google"

    def __init__(self, model) -> None:
        super().__init__(model)
        self.settings = get_settings()
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"
        self.timeout = self.settings.provider_timeout

    def is_available(self) -> bool:
        return bool(self.settings.google_api_key)

    def _convert_messages(self, messages: list[dict[str, str]]) -> tuple[str | None, list[dict]]:
        system_instruction: str | None = None
        contents: list[dict] = []
        for message in messages:
            if message["role"] == "system":
                system_instruction = message["content"]
                continue
            role = "model" if message["role"] == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": message["content"]}]})
        if not contents:
            contents = [{"role": "user", "parts": [{"text": "Hello"}]}]
        return system_instruction, contents

    async def generate(self, request: GenerationRequest) -> GenerationResponse:
        if not self.is_available():
            raise ProviderError(
                "Google API key is not configured. Set GOOGLE_API_KEY in your environment.",
                code=ProviderErrorCode.MISSING_API_KEY,
            )

        start = time.perf_counter()
        system_instruction, contents = self._convert_messages(request.messages)
        payload: dict = {
            "contents": contents,
            "generationConfig": {
                "maxOutputTokens": request.max_tokens,
                "temperature": request.temperature,
            },
        }
        if system_instruction:
            payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}

        url = f"{self.base_url}/models/{self.model.id}:generateContent"
        # Header rather than ?key= query param so the key never appears in logged URLs.
        headers = {"x-goog-api-key": self.settings.google_api_key}

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise ProviderError("Google request timed out.", code=ProviderErrorCode.TIMEOUT) from exc
        except httpx.RequestError as exc:
            raise ProviderError(
                f"Network error contacting Google: {exc}",
                code=ProviderErrorCode.NETWORK_ERROR,
            ) from exc

        if response.status_code == 429:
            raise ProviderError(
                "Google rate limit exceeded.",
                code=ProviderErrorCode.RATE_LIMIT,
                status_code=429,
            )

        if response.status_code >= 400:
            detail = response.text[:300]
            raise ProviderError(
                f"Google API error ({response.status_code}): {detail}",
                code=ProviderErrorCode.PROVIDER_ERROR,
                status_code=response.status_code,
            )

        data = response.json()
        try:
            candidates = data.get("candidates", [])
            parts = candidates[0]["content"]["parts"]
            content = "".join(part.get("text", "") for part in parts)
            usage_meta = data.get("usageMetadata", {})
            input_tokens = usage_meta.get("promptTokenCount", estimate_messages_tokens(request.messages))
            output_tokens = usage_meta.get("candidatesTokenCount", estimate_tokens(content))
            finish_reason = candidates[0].get("finishReason")
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(
                "Invalid response format from Google.",
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
