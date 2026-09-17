"""Scoped usage aggregation over the routing log.

Every routing-log row is a completed request: the log is written only after a
generation succeeds (failed requests raise before logging). `successful_requests`
therefore equals `total_requests` for now; it is reported separately so the response
shape doesn't change if failed requests are logged later.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from typing import Any

from app.db.repository import list_routing_logs_for_usage
from app.schemas.usage import UsageBreakdownEntry, UsageFilters, UsageSummary

logger = logging.getLogger(__name__)

UNSET_KEY = "(none)"


def _tags(row: dict[str, Any]) -> dict[str, str]:
    raw = row.get("tags_json")
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Skipping unreadable tags_json for request_id=%s", row.get("request_id"))
        return {}
    return {str(key): str(value) for key, value in parsed.items()} if isinstance(parsed, dict) else {}


def _matches_tag(row: dict[str, Any], tag_key: str | None, tag_value: str | None) -> bool:
    if tag_key is None:
        return True
    tags = _tags(row)
    if tag_key not in tags:
        return False
    return tag_value is None or tags[tag_key] == tag_value


def _totals(rows: list[dict[str, Any]]) -> dict[str, Any]:
    count = len(rows)
    latencies = [row["latency_ms"] for row in rows if row.get("latency_ms") is not None]
    return {
        "total_requests": count,
        "successful_requests": count,
        "fallback_requests": sum(1 for row in rows if row.get("fallback_used")),
        "total_estimated_cost": round(sum(row.get("actual_cost") or 0.0 for row in rows), 8),
        "average_latency_ms": round(sum(latencies) / len(latencies), 2) if latencies else 0.0,
    }


def _breakdown(groups: dict[str, list[dict[str, Any]]]) -> list[UsageBreakdownEntry]:
    entries = [UsageBreakdownEntry(key=key, **_totals(rows)) for key, rows in groups.items()]
    return sorted(entries, key=lambda entry: (-entry.total_requests, entry.key))


def _group(rows: Iterable[dict[str, Any]], key_fn) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        for key in key_fn(row):
            groups.setdefault(key, []).append(row)
    return groups


def get_usage_summary(filters: UsageFilters) -> UsageSummary:
    rows = list_routing_logs_for_usage(
        user_id=filters.user_id,
        session_id=filters.session_id,
        model_id=filters.model_id,
    )
    rows = [row for row in rows if _matches_tag(row, filters.tag_key, filters.tag_value)]

    return UsageSummary(
        filters=filters,
        **_totals(rows),
        by_user=_breakdown(_group(rows, lambda row: [row.get("user_id") or UNSET_KEY])),
        by_model=_breakdown(_group(rows, lambda row: [row.get("selected_model") or UNSET_KEY])),
        by_tag=_breakdown(
            _group(rows, lambda row: [f"{key}={value}" for key, value in sorted(_tags(row).items())])
        ),
    )
