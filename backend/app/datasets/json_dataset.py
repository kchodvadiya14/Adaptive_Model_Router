"""JSON benchmark dataset loader."""

from __future__ import annotations

import json
from pathlib import Path

from app.datasets.base import DatasetAdapter
from app.schemas.evaluation import BenchmarkPrompt


class JsonDatasetAdapter(DatasetAdapter):
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> list[BenchmarkPrompt]:
        if not self.path.exists():
            raise FileNotFoundError(f"Dataset not found: {self.path}")
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            raw = raw.get("prompts", [])
        return [BenchmarkPrompt.model_validate(item) for item in raw]
