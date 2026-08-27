"""Base model provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum

from pydantic import BaseModel, Field

from app.schemas.chat import CostBreakdown
from app.schemas.models import ModelMetadata
from app.utils.cost import calculate_cost


class ProviderErrorCode(str, Enum):
    MISSING_API_KEY = "missing_api_key"
    MODEL_UNAVAILABLE = "model_unavailable"
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    NETWORK_ERROR = "network_error"
    INVALID_RESPONSE = "invalid_response"
    PROVIDER_ERROR = "provider_error"


class ProviderError(Exception):
    """Raised when a provider fails to generate a response."""

    def __init__(
        self,
        message: str,
        code: ProviderErrorCode = ProviderErrorCode.PROVIDER_ERROR,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


class GenerationRequest(BaseModel):
    messages: list[dict[str, str]]
    max_tokens: int = Field(default=1024, ge=1, le=8192)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)


class GenerationResponse(BaseModel):
    content: str
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    latency_ms: float = Field(ge=0)
    finish_reason: str | None = None


class BaseModelProvider(ABC):
    """Common interface for all LLM provider adapters."""

    provider_name: str = "base"

    def __init__(self, model: ModelMetadata) -> None:
        self.model = model

    @abstractmethod
    async def generate(self, request: GenerationRequest) -> GenerationResponse:
        """Generate a completion from the provider."""

    @abstractmethod
    def is_available(self) -> bool:
        """Return True when the provider is configured and reachable."""

    def get_model_info(self) -> ModelMetadata:
        return self.model

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> CostBreakdown:
        return calculate_cost(input_tokens, output_tokens, self.model)
