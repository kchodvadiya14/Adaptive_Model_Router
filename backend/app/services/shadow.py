"""Shadow mode: record what the learned router *would* have chosen, without acting on it.

With SHADOW_ROUTER_ENABLED=true, every request is served exactly as before (pinned model or the
configured router). Afterwards the learned router is asked for its choice on the same prompt and the
comparison is stored. Nothing here changes the response, sends an extra provider request, or can fail
the request: it only reads history and writes one row.

What the summary can and cannot say. Agreement and the shadow model's *estimated* cost (had it
produced the same number of output tokens) are directly comparable to what was actually served.
The shadow model's quality is a prediction: it was never run, so its true quality is unknown.
Treat the numbers as a screening step before a live canary, not as measured savings.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from app.db.database import get_connection

logger = logging.getLogger(__name__)


def record_shadow_decision(
    *,
    request_id: str | None,
    task_type: str | None,
    served_by: str,
    actual_model: str,
    actual_cost: float,
    actual_quality: float | None,
    shadow_model: str,
    shadow_estimated_cost: float,
    shadow_estimated_quality: float,
    shadow_mode: str,
) -> None:
    try:
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO shadow_decisions (
                    timestamp, request_id, task_type, served_by, actual_model, actual_cost, actual_quality,
                    shadow_model, shadow_estimated_cost, shadow_estimated_quality, shadow_mode, agrees
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    datetime.now(UTC).isoformat(),
                    request_id,
                    task_type,
                    served_by,
                    actual_model,
                    actual_cost,
                    actual_quality,
                    shadow_model,
                    shadow_estimated_cost,
                    shadow_estimated_quality,
                    shadow_mode,
                    1 if shadow_model == actual_model else 0,
                ),
            )
            conn.commit()
    except Exception as exc:  # noqa: BLE001 - shadow logging must never affect a request
        logger.warning("[request_id=%s] Failed to record shadow decision: %s", request_id, exc)


def shadow_summary(limit: int | None = None) -> dict[str, Any]:
    """Aggregate comparison of shadow choices with what was actually served."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM shadow_decisions ORDER BY id DESC" + (" LIMIT ?" if limit else ""),
            (limit,) if limit else (),
        ).fetchall()
    n = len(rows)
    if n == 0:
        return {"requests": 0}

    def mean(values: list[float]) -> float | None:
        return round(sum(values) / len(values), 8) if values else None

    actual_cost = [r["actual_cost"] for r in rows]
    shadow_cost = [r["shadow_estimated_cost"] for r in rows]
    scored = [r for r in rows if r["actual_quality"] is not None]
    by_mode: dict[str, int] = {}
    for r in rows:
        by_mode[r["shadow_mode"]] = by_mode.get(r["shadow_mode"], 0) + 1
    by_task: dict[str, dict[str, Any]] = {}
    for r in rows:
        t = by_task.setdefault(r["task_type"] or "unknown", {"requests": 0, "agree": 0, "actual_cost": 0.0, "shadow_cost": 0.0})
        t["requests"] += 1
        t["agree"] += r["agrees"]
        t["actual_cost"] += r["actual_cost"]
        t["shadow_cost"] += r["shadow_estimated_cost"]
    return {
        "requests": n,
        "agreement_rate": round(sum(r["agrees"] for r in rows) / n, 4),
        "mean_actual_cost": mean(actual_cost),
        "mean_shadow_estimated_cost": mean(shadow_cost),
        "estimated_cost_change": round(sum(shadow_cost) / sum(actual_cost) - 1.0, 4) if sum(actual_cost) else None,
        "mean_actual_quality": mean([r["actual_quality"] for r in scored]),
        "mean_shadow_predicted_quality": mean([r["shadow_estimated_quality"] for r in rows]),
        "shadow_modes": by_mode,
        "by_task_type": {
            task: {
                "requests": v["requests"],
                "agreement_rate": round(v["agree"] / v["requests"], 4),
                "estimated_cost_change": round(v["shadow_cost"] / v["actual_cost"] - 1.0, 4) if v["actual_cost"] else None,
            }
            for task, v in sorted(by_task.items())
        },
        "note": "Shadow quality is predicted, never measured: the shadow model was not run. Validate with a live canary before claiming savings.",
    }
