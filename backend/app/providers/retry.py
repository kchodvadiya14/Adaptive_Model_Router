"""Retry helper for batch pipelines (dataset generation, benchmarks) on transient provider errors."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

from app.providers.base import ProviderError, ProviderErrorCode

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Reasoning models (GPT-OSS, Nemotron) spend part of max_tokens on hidden reasoning, so a
# tight cap truncates their answers and makes the judge penalise them unfairly.
BATCH_MAX_TOKENS = 2048

_TRANSIENT_CODES = {ProviderErrorCode.RATE_LIMIT, ProviderErrorCode.TIMEOUT, ProviderErrorCode.NETWORK_ERROR}


def is_transient(error: Exception) -> bool:
    if not isinstance(error, ProviderError):
        return False
    if error.code in _TRANSIENT_CODES:
        return True
    return error.status_code is not None and error.status_code >= 500


async def retry_transient(
    call: Callable[[], Awaitable[T]],
    *,
    attempts: int = 4,
    base_delay: float = 3.0,
) -> T:
    """Await ``call()``, retrying transient provider errors with exponential backoff."""
    for attempt in range(1, attempts + 1):
        try:
            return await call()
        except Exception as exc:
            if attempt == attempts or not is_transient(exc):
                raise
            delay = base_delay * 2 ** (attempt - 1)
            logger.warning("Transient provider error (attempt %d/%d), retrying in %.0fs: %s", attempt, attempts, delay, exc)
            await asyncio.sleep(delay)
    raise AssertionError("unreachable")
