"""Persist trained router artifacts and metadata."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import joblib

from app.schemas.training import RouterTrainType, TrainedModelInfo, TrainingMetrics

MODELS_DIR = Path("models")
REGISTRY_PATH = MODELS_DIR / "registry.json"


def ensure_models_dir() -> None:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)


def artifact_path(model_id: str, router_type: RouterTrainType) -> Path:
    return MODELS_DIR / f"{router_type.value}_{model_id}.joblib"


def save_artifact(model_id: str, router_type: RouterTrainType, payload: dict) -> Path:
    ensure_models_dir()
    path = artifact_path(model_id, router_type)
    joblib.dump(payload, path)
    return path


def load_artifact(model_id: str, router_type: RouterTrainType) -> dict | None:
    path = artifact_path(model_id, router_type)
    if not path.exists():
        return None
    return joblib.load(path)


def load_latest_artifact(router_type: RouterTrainType) -> dict | None:
    registry = load_registry()
    matches = [item for item in registry if item.router_type == router_type]
    if not matches:
        return None
    latest = sorted(matches, key=lambda item: item.created_at, reverse=True)[0]
    return load_artifact(latest.id, router_type)


def load_registry() -> list[TrainedModelInfo]:
    ensure_models_dir()
    if not REGISTRY_PATH.exists():
        return []
    raw = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    return [TrainedModelInfo.model_validate(item) for item in raw]


def register_model(info: TrainedModelInfo) -> TrainedModelInfo:
    registry = [item for item in load_registry() if item.id != info.id]
    registry.insert(0, info)
    REGISTRY_PATH.write_text(
        json.dumps([item.model_dump(mode="json") for item in registry], indent=2),
        encoding="utf-8",
    )
    return info


def get_model_info(model_id: str) -> TrainedModelInfo | None:
    for item in load_registry():
        if item.id == model_id:
            return item
    return None
