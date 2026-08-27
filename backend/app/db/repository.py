"""Persistence layer for routing logs and benchmark reports."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from app.db.database import get_connection
from app.schemas.evaluation import BenchmarkReport, MetricsSummary


def _hash_prompt(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def log_routing_event(
    *,
    prompt: str,
    task_type: str | None,
    difficulty: float | None,
    router_type: str,
    selected_model: str,
    model_tier: str,
    estimated_cost: float,
    actual_cost: float,
    estimated_quality: float | None,
    actual_quality: float | None,
    latency_ms: float,
    routed: bool,
    strong_baseline_cost: float,
    input_tokens: int = 0,
    output_tokens: int = 0,
    store_prompt: bool = False,
    fallback_used: bool = False,
    fallback_attempts: int = 1,
    original_model: str | None = None,
    fallback_reason: str | None = None,
) -> int:
    prompt_hash = _hash_prompt(prompt if store_prompt else prompt[:128])
    timestamp = datetime.now(UTC).isoformat()
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO routing_logs (
                timestamp, prompt_hash, task_type, difficulty, router_type,
                selected_model, model_tier, estimated_cost, actual_cost,
                estimated_quality, actual_quality, latency_ms, routed,
                strong_baseline_cost, input_tokens, output_tokens,
                fallback_used, fallback_attempts, original_model, fallback_reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                timestamp,
                prompt_hash,
                task_type,
                difficulty,
                router_type,
                selected_model,
                model_tier,
                estimated_cost,
                actual_cost,
                estimated_quality,
                actual_quality,
                latency_ms,
                1 if routed else 0,
                strong_baseline_cost,
                input_tokens,
                output_tokens,
                1 if fallback_used else 0,
                fallback_attempts,
                original_model,
                fallback_reason,
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)


def get_metrics_summary() -> MetricsSummary:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM routing_logs ORDER BY id DESC").fetchall()

    if not rows:
        return MetricsSummary(
            total_requests=0,
            total_cost=0.0,
            average_cost=0.0,
            average_quality=None,
            quality_retention=None,
            cost_saved=0.0,
            average_latency_ms=0.0,
            strong_model_usage=0.0,
            fallback_rate=0.0,
            requests_by_model={},
            requests_by_task={},
            requests_by_tier={},
        )

    total = len(rows)
    total_cost = sum(row["actual_cost"] or 0 for row in rows)
    avg_cost = total_cost / total
    avg_latency = sum(row["latency_ms"] or 0 for row in rows) / total
    strong_cost_sum = sum(row["strong_baseline_cost"] or 0 for row in rows)
    cost_saved = max(0.0, strong_cost_sum - total_cost)

    qualities = [row["actual_quality"] for row in rows if row["actual_quality"] is not None]
    avg_quality = sum(qualities) / len(qualities) if qualities else None

    strong_qualities = [
        row["actual_quality"]
        for row in rows
        if row["actual_quality"] is not None and row["model_tier"] == "strong"
    ]
    quality_retention = None
    if avg_quality is not None and strong_qualities:
        strong_avg = sum(strong_qualities) / len(strong_qualities)
        if strong_avg > 0:
            quality_retention = round(avg_quality / strong_avg, 4)

    requests_by_model: dict[str, int] = {}
    requests_by_task: dict[str, int] = {}
    requests_by_tier: dict[str, int] = {}
    strong_usage = 0
    fallback_usage = 0
    for row in rows:
        requests_by_model[row["selected_model"]] = requests_by_model.get(row["selected_model"], 0) + 1
        if row["task_type"]:
            requests_by_task[row["task_type"]] = requests_by_task.get(row["task_type"], 0) + 1
        if row["model_tier"]:
            requests_by_tier[row["model_tier"]] = requests_by_tier.get(row["model_tier"], 0) + 1
        if row["model_tier"] == "strong":
            strong_usage += 1
        if "fallback_used" in row.keys() and row["fallback_used"]:
            fallback_usage += 1

    return MetricsSummary(
        total_requests=total,
        total_cost=round(total_cost, 8),
        average_cost=round(avg_cost, 8),
        average_quality=round(avg_quality, 4) if avg_quality is not None else None,
        quality_retention=quality_retention,
        cost_saved=round(cost_saved, 8),
        average_latency_ms=round(avg_latency, 2),
        strong_model_usage=round(strong_usage / total, 4),
        fallback_rate=round(fallback_usage / total, 4),
        requests_by_model=requests_by_model,
        requests_by_task=requests_by_task,
        requests_by_tier=requests_by_tier,
    )


def save_benchmark_report(report: BenchmarkReport) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO benchmark_reports (id, created_at, dataset_path, quality_floor, report_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                report.id,
                report.created_at,
                report.dataset_path,
                report.quality_floor,
                report.model_dump_json(),
            ),
        )
        conn.commit()


def list_benchmark_reports(limit: int = 20) -> list[BenchmarkReport]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT report_json FROM benchmark_reports ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [BenchmarkReport.model_validate_json(row["report_json"]) for row in rows]


def get_benchmark_report(report_id: str) -> BenchmarkReport | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT report_json FROM benchmark_reports WHERE id = ?",
            (report_id,),
        ).fetchone()
    if not row:
        return None
    return BenchmarkReport.model_validate_json(row["report_json"])
