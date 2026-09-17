"""Persistence for per-attempt model outcomes (historical routing performance).

One row per generation attempt the gateway sends to a provider — initial, fallback, or
escalation — separate from routing_logs, which stays one row per completed request.
Same connection pattern as the other repositories: a fresh connection per call.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.db.database import get_connection

OUTCOME_SUCCESS = "success"
OUTCOME_QUALITY_FAILURE = "quality_failure"
OUTCOME_RETRYABLE_FAILURE = "retryable_failure"
OUTCOME_NON_RETRYABLE_FAILURE = "non_retryable_failure"
OUTCOME_TIMEOUT = "timeout"

ALL_OUTCOMES = (
    OUTCOME_SUCCESS,
    OUTCOME_QUALITY_FAILURE,
    OUTCOME_RETRYABLE_FAILURE,
    OUTCOME_NON_RETRYABLE_FAILURE,
    OUTCOME_TIMEOUT,
)


def record_outcome(
    *,
    model_id: str,
    provider: str,
    stage: str,
    outcome: str,
    success: bool,
    request_id: str | None = None,
    model_tier: str | None = None,
    task_type: str | None = None,
    difficulty: float | None = None,
    error_code: str | None = None,
    latency_ms: float | None = None,
    estimated_cost: float | None = None,
    quality_score: float | None = None,
    recorded_at: datetime | None = None,
) -> int:
    if outcome not in ALL_OUTCOMES:
        raise ValueError(f"Unknown outcome '{outcome}'")
    moment = recorded_at or datetime.now(UTC)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO model_outcomes (
                timestamp, recorded_at, request_id, model_id, provider, model_tier,
                task_type, difficulty, stage, outcome, success, error_code,
                latency_ms, estimated_cost, quality_score, fallback_used
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (
                moment.astimezone(UTC).isoformat(),
                moment.timestamp(),
                request_id,
                model_id,
                provider,
                model_tier,
                task_type,
                difficulty,
                stage,
                outcome,
                1 if success else 0,
                error_code,
                latency_ms,
                estimated_cost,
                quality_score,
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)


def set_quality(outcome_id: int, quality_score: float | None, *, quality_failure: bool) -> None:
    """Attach the judge's score to a successful attempt; a score below the escalation
    threshold turns its outcome into `quality_failure` (the generation still succeeded)."""
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE model_outcomes
            SET quality_score = ?,
                outcome = CASE WHEN ? = 1 AND success = 1 THEN 'quality_failure' ELSE outcome END
            WHERE id = ?
            """,
            (quality_score, 1 if quality_failure else 0, outcome_id),
        )
        conn.commit()


def mark_fallback_used(outcome_id: int) -> None:
    """The gateway moved on from this attempt to another model."""
    with get_connection() as conn:
        conn.execute("UPDATE model_outcomes SET fallback_used = 1 WHERE id = ?", (outcome_id,))
        conn.commit()


def list_outcomes(request_id: str | None = None) -> list[dict[str, Any]]:
    query = "SELECT * FROM model_outcomes"
    params: list[Any] = []
    if request_id is not None:
        query += " WHERE request_id = ?"
        params.append(request_id)
    with get_connection() as conn:
        rows = conn.execute(f"{query} ORDER BY id", params).fetchall()
    return [dict(row) for row in rows]


def aggregate_by_model(
    *,
    model_id: str | None = None,
    task_type: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> list[dict[str, Any]]:
    """Per-model aggregates computed in SQL, so reporting never loads every row."""
    clauses: list[str] = []
    params: list[Any] = []
    if model_id is not None:
        clauses.append("model_id = ?")
        params.append(model_id)
    if task_type is not None:
        clauses.append("task_type = ?")
        params.append(task_type)
    if since is not None:
        clauses.append("recorded_at >= ?")
        params.append(since.timestamp())
    if until is not None:
        clauses.append("recorded_at <= ?")
        params.append(until.timestamp())
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    # Distinct prefix: "success_count" is already the SUM(success) column below.
    outcome_columns = ",\n".join(
        f"SUM(CASE WHEN outcome = '{name}' THEN 1 ELSE 0 END) AS outcome_{name}" for name in ALL_OUTCOMES
    )
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT model_id,
                   MAX(provider) AS provider,
                   COUNT(*) AS request_count,
                   SUM(success) AS success_count,
                   {outcome_columns},
                   AVG(CASE WHEN success = 1 THEN latency_ms END) AS average_latency_ms,
                   AVG(estimated_cost) AS average_estimated_cost,
                   AVG(quality_score) AS average_quality_score,
                   SUM(fallback_used) AS fallback_count,
                   MIN(recorded_at) AS first_recorded_at,
                   MAX(recorded_at) AS last_recorded_at
            FROM model_outcomes
            {where}
            GROUP BY model_id
            ORDER BY request_count DESC, model_id
            """,
            params,
        ).fetchall()
    return [dict(row) for row in rows]
