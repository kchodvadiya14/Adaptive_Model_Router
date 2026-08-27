"""Preference dataset file storage."""

from __future__ import annotations

import json
from pathlib import Path

from app.schemas.dataset import DatasetManifest, PreferenceRecord

DATASETS_DIR = Path("data/processed/datasets")
INDEX_PATH = DATASETS_DIR / "index.json"


def ensure_dirs() -> None:
    DATASETS_DIR.mkdir(parents=True, exist_ok=True)


def dataset_path(dataset_id: str) -> Path:
    return DATASETS_DIR / f"{dataset_id}.jsonl"


def load_index() -> list[DatasetManifest]:
    ensure_dirs()
    if not INDEX_PATH.exists():
        return []
    raw = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    return [DatasetManifest.model_validate(item) for item in raw]


def save_index(manifests: list[DatasetManifest]) -> None:
    ensure_dirs()
    payload = [item.model_dump(mode="json") for item in manifests]
    INDEX_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def add_manifest(manifest: DatasetManifest) -> None:
    manifests = load_index()
    manifests = [item for item in manifests if item.id != manifest.id]
    manifests.insert(0, manifest)
    save_index(manifests)


def get_manifest(dataset_id: str) -> DatasetManifest | None:
    for manifest in load_index():
        if manifest.id == dataset_id:
            return manifest
    return None


def save_records(dataset_id: str, records: list[PreferenceRecord]) -> Path:
    path = dataset_path(dataset_id)
    ensure_dirs()
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(record.model_dump_json())
            handle.write("\n")
    return path


def load_records(dataset_id: str) -> list[PreferenceRecord]:
    path = dataset_path(dataset_id)
    if not path.exists():
        return []
    records: list[PreferenceRecord] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(PreferenceRecord.model_validate_json(line))
    return records


def update_record(dataset_id: str, updated: PreferenceRecord) -> None:
    records = load_records(dataset_id)
    replaced = False
    for index, record in enumerate(records):
        if record.id == updated.id:
            records[index] = updated
            replaced = True
            break
    if not replaced:
        raise KeyError(f"Record '{updated.id}' not found")
    save_records(dataset_id, records)
