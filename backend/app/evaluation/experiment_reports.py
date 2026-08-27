"""Experiment report persistence."""

from __future__ import annotations

import json
from pathlib import Path

from app.schemas.experiments import ExperimentReport

REPORTS_DIR = Path("experiments/reports")
INDEX_PATH = REPORTS_DIR / "index.json"


def save_experiment_report(report: ExperimentReport) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / f"{report.id}.json"
    path.write_text(report.model_dump_json(indent=2), encoding="utf-8")

    index = _load_index()
    index[report.id] = {
        "id": report.id,
        "name": report.name,
        "experiment_type": report.experiment_type,
        "created_at": report.created_at,
        "dataset_path": report.dataset_path,
    }
    INDEX_PATH.write_text(json.dumps(index, indent=2), encoding="utf-8")
    return path


def load_experiment_report(report_id: str) -> ExperimentReport | None:
    path = REPORTS_DIR / f"{report_id}.json"
    if not path.exists():
        return None
    return ExperimentReport.model_validate_json(path.read_text(encoding="utf-8"))


def list_experiment_reports(limit: int = 20) -> list[dict]:
    index = _load_index()
    items = sorted(index.values(), key=lambda item: item["created_at"], reverse=True)
    return items[:limit]


def _load_index() -> dict[str, dict]:
    if not INDEX_PATH.exists():
        return {}
    return json.loads(INDEX_PATH.read_text(encoding="utf-8"))
