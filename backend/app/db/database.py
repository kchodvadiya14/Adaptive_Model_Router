"""SQLite database initialization and helpers."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from app.config.settings import get_settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS routing_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    prompt_hash TEXT NOT NULL,
    task_type TEXT,
    difficulty REAL,
    router_type TEXT,
    selected_model TEXT,
    model_tier TEXT,
    estimated_cost REAL,
    actual_cost REAL,
    estimated_quality REAL,
    actual_quality REAL,
    latency_ms REAL,
    routed INTEGER DEFAULT 0,
    strong_baseline_cost REAL,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS benchmark_reports (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    dataset_path TEXT NOT NULL,
    quality_floor REAL NOT NULL,
    report_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    job_type TEXT NOT NULL,
    status TEXT NOT NULL,
    progress REAL NOT NULL DEFAULT 0.0,
    error TEXT,
    result_json TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_jobs_job_type ON jobs (job_type);

CREATE TABLE IF NOT EXISTS model_outcomes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    recorded_at REAL NOT NULL,
    request_id TEXT,
    model_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    model_tier TEXT,
    task_type TEXT,
    difficulty REAL,
    stage TEXT NOT NULL,
    outcome TEXT NOT NULL,
    success INTEGER NOT NULL,
    error_code TEXT,
    latency_ms REAL,
    estimated_cost REAL,
    quality_score REAL,
    fallback_used INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_model_outcomes_model_time ON model_outcomes (model_id, recorded_at);
CREATE INDEX IF NOT EXISTS idx_model_outcomes_task_time ON model_outcomes (task_type, recorded_at);
CREATE INDEX IF NOT EXISTS idx_model_outcomes_request_id ON model_outcomes (request_id);

CREATE TABLE IF NOT EXISTS model_health (
    model_id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'closed',
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    recent_failures INTEGER NOT NULL DEFAULT 0,
    recent_successes INTEGER NOT NULL DEFAULT 0,
    opened_at REAL,
    last_success REAL,
    last_failure REAL,
    last_error TEXT
);
"""

MIGRATIONS = [
    "ALTER TABLE routing_logs ADD COLUMN fallback_used INTEGER DEFAULT 0",
    "ALTER TABLE routing_logs ADD COLUMN fallback_attempts INTEGER DEFAULT 1",
    "ALTER TABLE routing_logs ADD COLUMN original_model TEXT",
    "ALTER TABLE routing_logs ADD COLUMN fallback_reason TEXT",
    # Request metadata for scoped usage reporting. Pre-existing rows get NULLs.
    "ALTER TABLE routing_logs ADD COLUMN request_id TEXT",
    "ALTER TABLE routing_logs ADD COLUMN user_id TEXT",
    "ALTER TABLE routing_logs ADD COLUMN session_id TEXT",
    "ALTER TABLE routing_logs ADD COLUMN tags_json TEXT",
    "ALTER TABLE routing_logs ADD COLUMN preferred_model TEXT",
    "CREATE INDEX IF NOT EXISTS idx_routing_logs_user_id ON routing_logs (user_id)",
    "CREATE INDEX IF NOT EXISTS idx_routing_logs_session_id ON routing_logs (session_id)",
    "CREATE INDEX IF NOT EXISTS idx_routing_logs_request_id ON routing_logs (request_id)",
]


def get_db_path() -> Path:
    settings = get_settings()
    url = settings.database_url
    if url.startswith("sqlite:///"):
        raw = url.replace("sqlite:///", "", 1)
        return Path(raw)
    raise ValueError(f"Unsupported database URL: {url}")


def init_db() -> None:
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(SCHEMA)
        for statement in MIGRATIONS:
            try:
                conn.execute(statement)
            except sqlite3.OperationalError:
                pass
        conn.commit()


def get_connection() -> sqlite3.Connection:
    init_db()
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    return conn
