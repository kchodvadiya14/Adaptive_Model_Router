"""Dataset adapter interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.schemas.evaluation import BenchmarkPrompt


class DatasetAdapter(ABC):
    @abstractmethod
    def load(self) -> list[BenchmarkPrompt]:
        """Load benchmark prompts from a data source."""
