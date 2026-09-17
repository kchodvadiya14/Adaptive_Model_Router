"""End-to-end request deadline.

`timeout_ms` is one overall budget for a request. A single RequestDeadline is created
when the request starts and is consulted before, and enforced around, every
awaitable step — initial generation, provider-error fallback, quality evaluation, and
quality escalation — so later steps only get whatever time is left.

This is deliberately separate from Step 6's `max_latency_ms`, which is a routing
constraint on a model's *average* latency metadata. `timeout_ms` bounds actual
wall-clock execution.

Deadline exhaustion is not a provider failure: `RequestTimeoutError` is not a
`ProviderError`, so it is never matched by fallback's `except ProviderError` and never
reaches health recording.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable
from dataclasses import dataclass
from typing import Any, TypeVar

T = TypeVar("T")

STAGE_GENERATION = "generation"
STAGE_FALLBACK = "fallback"
STAGE_EVALUATION = "evaluation"
STAGE_ESCALATION = "escalation"


class RequestTimeoutError(Exception):
    """The request's overall timeout_ms budget ran out."""

    def __init__(
        self,
        *,
        stage: str,
        timeout_ms: float,
        elapsed_ms: float,
        remaining_ms: float,
        request_id: str | None = None,
        model_id: str | None = None,
        started: bool,
    ) -> None:
        target = f" for model '{model_id}'" if model_id else ""
        if started:
            detail = f"exceeded the request timeout of {timeout_ms:.0f}ms during {stage}{target}"
        else:
            detail = (
                f"did not start {stage}{target}: {remaining_ms:.0f}ms of the "
                f"{timeout_ms:.0f}ms request timeout remained"
            )
        super().__init__(f"Request {detail} (elapsed {elapsed_ms:.0f}ms).")
        self.stage = stage
        self.timeout_ms = timeout_ms
        self.elapsed_ms = elapsed_ms
        self.remaining_ms = remaining_ms
        self.request_id = request_id
        self.model_id = model_id
        self.started = started

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": "request_timeout",
            "message": str(self),
            "request_id": self.request_id,
            "stage": self.stage,
            "model_id": self.model_id,
            "timeout_ms": round(self.timeout_ms, 2),
            "elapsed_ms": round(self.elapsed_ms, 2),
            "remaining_ms": round(max(0.0, self.remaining_ms), 2),
        }


@dataclass
class RequestDeadline:
    timeout_ms: float
    min_attempt_budget_ms: float
    request_id: str | None = None
    started_at: float = 0.0

    @classmethod
    def start(
        cls,
        timeout_ms: float,
        *,
        min_attempt_budget_ms: float,
        request_id: str | None = None,
    ) -> "RequestDeadline":
        return cls(
            timeout_ms=float(timeout_ms),
            min_attempt_budget_ms=float(min_attempt_budget_ms),
            request_id=request_id,
            started_at=time.monotonic(),
        )

    def elapsed_ms(self) -> float:
        return (time.monotonic() - self.started_at) * 1000.0

    def remaining_ms(self) -> float:
        return self.timeout_ms - self.elapsed_ms()

    def _error(self, stage: str, model_id: str | None, *, started: bool) -> RequestTimeoutError:
        elapsed = self.elapsed_ms()
        return RequestTimeoutError(
            stage=stage,
            timeout_ms=self.timeout_ms,
            elapsed_ms=elapsed,
            remaining_ms=self.timeout_ms - elapsed,
            request_id=self.request_id,
            model_id=model_id,
            started=started,
        )

    def ensure_budget(self, stage: str, model_id: str | None = None) -> float:
        """Raise before starting a step when too little time is left for it to be
        worth attempting. Returns the remaining budget in ms."""
        remaining = self.remaining_ms()
        if remaining < self.min_attempt_budget_ms:
            raise self._error(stage, model_id, started=False)
        return remaining

    async def run(self, awaitable: Awaitable[T], stage: str, model_id: str | None = None) -> T:
        """Await `awaitable` bounded by the remaining budget. Cancels it on expiry."""
        try:
            remaining = self.ensure_budget(stage, model_id)
        except RequestTimeoutError:
            if asyncio.iscoroutine(awaitable):
                awaitable.close()  # never started; avoid "coroutine was never awaited"
            raise
        try:
            return await asyncio.wait_for(awaitable, timeout=remaining / 1000.0)
        except TimeoutError as exc:
            raise self._error(stage, model_id, started=True) from exc


async def run_within(
    deadline: RequestDeadline | None,
    awaitable: Awaitable[T],
    stage: str,
    model_id: str | None = None,
) -> T:
    """`deadline.run(...)` when a deadline is set; a plain await otherwise, so requests
    without timeout_ms behave exactly as before."""
    if deadline is None:
        return await awaitable
    return await deadline.run(awaitable, stage, model_id)
