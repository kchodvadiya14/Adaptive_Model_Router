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
"""

MIGRATIONS = [
    "ALTER TABLE routing_logs ADD COLUMN fallback_used INTEGER DEFAULT 0",
    "ALTER TABLE routing_logs ADD COLUMN fallback_attempts INTEGER DEFAULT 1",
    "ALTER TABLE routing_logs ADD COLUMN original_model TEXT",
    "ALTER TABLE routing_logs ADD COLUMN fallback_reason TEXT",
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
