"""Benchmark report persistence helpers."""

from __future__ import annotations

import json
from pathlib import Path

from app.schemas.evaluation import BenchmarkReport

REPORTS_DIR = Path("experiments/benchmarks")


def save_report_file(report: BenchmarkReport) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / f"{report.id}.json"
    path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return path


def load_report_file(report_id: str) -> BenchmarkReport | None:
    path = REPORTS_DIR / f"{report_id}.json"
    if not path.exists():
        return None
    return BenchmarkReport.model_validate_json(path.read_text(encoding="utf-8"))


def list_report_files() -> list[str]:
    if not REPORTS_DIR.exists():
        return []
    return sorted(path.stem for path in REPORTS_DIR.glob("*.json"))
