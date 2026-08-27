"""Shared provider error mapping for HTTP APIs."""

from fastapi import HTTPException, status

from app.providers.base import ProviderError, ProviderErrorCode

ERROR_STATUS_MAP = {
    ProviderErrorCode.MISSING_API_KEY: status.HTTP_503_SERVICE_UNAVAILABLE,
    ProviderErrorCode.MODEL_UNAVAILABLE: status.HTTP_404_NOT_FOUND,
    ProviderErrorCode.TIMEOUT: status.HTTP_504_GATEWAY_TIMEOUT,
    ProviderErrorCode.RATE_LIMIT: status.HTTP_429_TOO_MANY_REQUESTS,
    ProviderErrorCode.NETWORK_ERROR: status.HTTP_502_BAD_GATEWAY,
    ProviderErrorCode.INVALID_RESPONSE: status.HTTP_502_BAD_GATEWAY,
    ProviderErrorCode.PROVIDER_ERROR: status.HTTP_502_BAD_GATEWAY,
}


def raise_provider_http_error(exc: ProviderError) -> None:
    http_status = ERROR_STATUS_MAP.get(exc.code, status.HTTP_500_INTERNAL_SERVER_ERROR)
    raise HTTPException(status_code=http_status, detail=exc.message) from exc
