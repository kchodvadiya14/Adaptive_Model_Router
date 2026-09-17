"""Persistence layer for generic background job state.

Follows the same pattern as app/db/repository.py: a fresh sqlite3 connection per
call via get_connection(), autocommit disabled, explicit commit. No new concurrency
model is introduced here.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.db.database import get_connection


def _now() -> str:
    return datetime.now(UTC).isoformat()


def create_job(job_id: str, job_type: str) -> None:
    now = _now()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO jobs (job_id, job_type, status, progress, error, result_json, created_at, started_at, completed_at)
            VALUES (?, ?, 'queued', 0.0, NULL, NULL, ?, NULL, NULL)
            """,
            (job_id, job_type, now),
        )
        conn.commit()


def update_job(
    job_id: str,
    *,
    status: str | None = None,
    progress: float | None = None,
    error: str | None = None,
    clear_error: bool = False,
    result_json: str | None = None,
    set_started_now: bool = False,
    set_completed_now: bool = False,
) -> None:
    """Partial update; only the fields passed are written."""
    fields: list[str] = []
    values: list[Any] = []

    if status is not None:
        fields.append("status = ?")
        values.append(status)
    if progress is not None:
        fields.append("progress = ?")
        values.append(progress)
    if error is not None:
        fields.append("error = ?")
        values.append(error)
    elif clear_error:
        fields.append("error = NULL")
    if result_json is not None:
        fields.append("result_json = ?")
        values.append(result_json)
    if set_started_now:
        fields.append("started_at = ?")
        values.append(_now())
    if set_completed_now:
        fields.append("completed_at = ?")
        values.append(_now())

    if not fields:
        return

    values.append(job_id)
    with get_connection() as conn:
        conn.execute(f"UPDATE jobs SET {', '.join(fields)} WHERE job_id = ?", values)
        conn.commit()


def get_job(job_id: str, job_type: str | None = None) -> dict[str, Any] | None:
    query = "SELECT * FROM jobs WHERE job_id = ?"
    params: list[Any] = [job_id]
    if job_type is not None:
        query += " AND job_type = ?"
        params.append(job_type)
    with get_connection() as conn:
        row = conn.execute(query, params).fetchone()
    return dict(row) if row else None


def mark_stale_jobs_failed(job_type: str, message: str) -> int:
    """Called once when a JobManager for ``job_type`` is constructed (i.e. on process
    startup, for the module-level singletons).

    Any job still 'queued' or 'running' belonged to a previous process — the asyncio
    task that would have finished it no longer exists. It must never be silently left
    as 'running' forever, and must never be reported as 'completed'. It is marked
    'failed' (the existing status convention already used for job errors) with a
    message identifying it as an interrupted-by-restart job rather than a real failure.
    """
    with get_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE jobs
            SET status = 'failed', progress = 1.0, error = ?, completed_at = ?
            WHERE job_type = ? AND status IN ('queued', 'running')
            """,
            (message, _now(), job_type),
        )
        conn.commit()
        return cursor.rowcount
