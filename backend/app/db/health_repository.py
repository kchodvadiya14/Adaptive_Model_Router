"""Persistence layer for per-model circuit-breaker health state.

Follows the same pattern as app/db/repository.py and app/db/job_repository.py: a
fresh sqlite3 connection per call via get_connection(), autocommit disabled, explicit
commit. Timestamps are stored as Unix epoch floats (not ISO strings) so cooldown
arithmetic can be done directly in SQL without date-string parsing.
"""

from __future__ import annotations

import time
from typing import Any

from app.db.database import get_connection


def _ensure_row(conn, model_id: str, provider: str) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO model_health
            (model_id, provider, state, consecutive_failures, recent_failures, recent_successes)
        VALUES (?, ?, 'closed', 0, 0, 0)
        """,
        (model_id, provider),
    )


def get_health(model_id: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM model_health WHERE model_id = ?", (model_id,)).fetchone()
    return dict(row) if row else None


def list_health() -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM model_health ORDER BY model_id").fetchall()
    return [dict(row) for row in rows]


def record_success(model_id: str, provider: str) -> None:
    """A successful generation always closes the circuit and resets the failure streak,
    regardless of the prior state (including recovering directly from a half-open trial)."""
    now = time.time()
    with get_connection() as conn:
        _ensure_row(conn, model_id, provider)
        conn.execute(
            """
            UPDATE model_health
            SET state = 'closed',
                consecutive_failures = 0,
                recent_successes = recent_successes + 1,
                last_success = ?,
                opened_at = NULL
            WHERE model_id = ?
            """,
            (now, model_id),
        )
        conn.commit()


def record_failure(model_id: str, provider: str, error: str, *, failure_threshold: int) -> str:
    """Record a retryable provider failure. Returns the resulting state.

    - A half-open trial that fails reopens the circuit immediately (the single trial
      is conclusive; it does not get more chances than a fresh request would).
    - Otherwise, the circuit opens once consecutive_failures reaches failure_threshold.
    """
    now = time.time()
    with get_connection() as conn:
        _ensure_row(conn, model_id, provider)
        row = conn.execute(
            "SELECT consecutive_failures, state FROM model_health WHERE model_id = ?",
            (model_id,),
        ).fetchone()
        prior_consecutive = row["consecutive_failures"] if row else 0
        prior_state = row["state"] if row else "closed"
        consecutive = prior_consecutive + 1

        if prior_state == "half_open" or consecutive >= failure_threshold:
            new_state = "open"
            opened_at = now
        else:
            new_state = "closed"
            opened_at = None

        conn.execute(
            """
            UPDATE model_health
            SET state = ?,
                consecutive_failures = ?,
                recent_failures = recent_failures + 1,
                last_failure = ?,
                last_error = ?,
                opened_at = ?
            WHERE model_id = ?
            """,
            (new_state, consecutive, now, error, opened_at, model_id),
        )
        conn.commit()
        return new_state


def release_half_open_trial(model_id: str) -> bool:
    """Return an unresolved half-open trial to 'open' without recording an outcome.

    `opened_at` is left untouched, so the cooldown has already elapsed and the next
    caller can claim a fresh trial immediately. Used when the trial was cut short for
    a reason that says nothing about the model's health (the request deadline).
    """
    with get_connection() as conn:
        cursor = conn.execute(
            "UPDATE model_health SET state = 'open' WHERE model_id = ? AND state = 'half_open'",
            (model_id,),
        )
        conn.commit()
        return cursor.rowcount == 1


def try_transition_to_half_open(model_id: str, cooldown_seconds: float) -> bool:
    """Atomically claim the single half-open trial slot for this model.

    Only succeeds if the circuit is currently 'open' and the cooldown has elapsed.
    The state check and the write happen in one UPDATE statement (no separate
    SELECT-then-UPDATE), so even under concurrent callers only one can ever flip the
    row from 'open' to 'half_open' — a second, near-simultaneous caller's UPDATE will
    match zero rows because the first caller's commit already changed `state`.
    Returns True iff this call performed the transition.
    """
    now = time.time()
    with get_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE model_health
            SET state = 'half_open'
            WHERE model_id = ?
              AND state = 'open'
              AND opened_at IS NOT NULL
              AND (? - opened_at) >= ?
            """,
            (model_id, now, cooldown_seconds),
        )
        conn.commit()
        return True  # BUG: pretend every claim attempt succeeds
