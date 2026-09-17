"""Regression tests: persistent developer state can't affect tests, and tests can't
affect each other through the database, registry, or file outputs.

The real developer database is never written here. "Persistent" state is simulated by
seeding a separate SQLite file and pointing the app at it, then switching to an isolated
database the same way the autouse fixture does.
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path

from app.datasets import storage
from app.db.database import get_connection, get_db_path
from app.db.repository import log_routing_event
from app.models.registry import get_model_registry
from app.router import health
from app.router.health import CircuitState
from app.schemas.usage import UsageFilters
from app.services.jobs import JobManager
from app.services.usage import get_usage_summary
from tests.conftest import use_isolated_database


def _count(table: str) -> int:
    with get_connection() as conn:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def _seed_persistent_style_state() -> None:
    """The kind of state a developer's long-lived database accumulates."""
    far_future = time.time() + 10 * 24 * 3600
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO model_health (model_id, provider, state, consecutive_failures,
                   recent_failures, recent_successes, opened_at, last_failure, last_error)
               VALUES ('mock-echo', 'mock', 'open', 99, 99, 0, ?, ?, 'persistent failure')""",
            (far_future, time.time()),
        )
        conn.commit()
    JobManager(job_type="unit_test").create_job()
    log_routing_event(
        prompt="seed", task_type=None, difficulty=None, router_type="rule_based",
        selected_model="mock-echo", model_tier="small", estimated_cost=1.0, actual_cost=1.0,
        estimated_quality=None, actual_quality=None, latency_ms=999.0, routed=True,
        strong_baseline_cost=1.0, user_id="alice", tags={"app": "chat"},
    )


def _assert_clean_state() -> None:
    assert _count("model_health") == 0
    assert _count("jobs") == 0
    assert _count("routing_logs") == 0
    assert health.get_model_health("mock-echo", "mock").state == CircuitState.CLOSED
    assert health.is_routable("mock-echo") == (True, None)
    assert get_usage_summary(UsageFilters()).total_requests == 0


def test_active_database_is_never_the_persistent_one(persistent_paths, isolated_state):
    active = get_db_path().resolve()
    assert active != persistent_paths.database
    assert Path(isolated_state) in active.parents


def test_fresh_test_starts_with_empty_state():
    _assert_clean_state()
    registry = get_model_registry()
    assert registry.get_model("mock-echo").enabled is True
    assert storage.load_index() == []


def test_seeded_persistent_database_does_not_leak_into_isolated_test(tmp_path, monkeypatch):
    persistent_db = use_isolated_database(tmp_path / "developer", monkeypatch)
    persistent_db.parent.mkdir()
    _seed_persistent_style_state()
    # Sanity-check the seed really makes mock-echo unusable in that database.
    assert health.is_routable("mock-echo")[0] is False
    assert _count("routing_logs") == 1
    seeded_hash = hashlib.sha256(persistent_db.read_bytes()).hexdigest()

    fresh_dir = tmp_path / "fresh"
    fresh_dir.mkdir()
    use_isolated_database(fresh_dir, monkeypatch)

    _assert_clean_state()
    assert hashlib.sha256(persistent_db.read_bytes()).hexdigest() == seeded_hash  # untouched


def test_state_written_by_one_test_part_1_writes():
    """Paired with part 2 below (pytest runs a file's tests in definition order)."""
    config = health.get_health_config()
    for _ in range(config.failure_threshold):
        health.record_failure("mock-echo", "mock", "left behind by part 1", config=config)
    JobManager(job_type="unit_test").mark_running(JobManager(job_type="unit_test").create_job())
    storage.ensure_dirs()
    storage.INDEX_PATH.write_text('[{"leftover": true}]', encoding="utf-8")
    get_model_registry().set_enabled("mock-echo", enabled=False)

    assert health.get_model_health("mock-echo", "mock").state == CircuitState.OPEN


def test_state_written_by_one_test_part_2_is_not_visible():
    _assert_clean_state()
    assert not storage.INDEX_PATH.exists()
    assert get_model_registry().get_model("mock-echo").enabled is True
