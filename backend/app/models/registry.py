"""Central model registry for discovering and managing LLM metadata."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from app.config.settings import Settings, get_settings
from app.schemas.models import ModelCreateRequest, ModelMetadata, ModelTier, ModelType, ModelUpdateRequest

logger = logging.getLogger(__name__)

DEFAULT_MODELS: list[ModelMetadata] = [
    ModelMetadata(
        id="gpt-4o-mini",
        name="GPT-4o Mini",
        provider="openai",
        type=ModelType.API,
        tier=ModelTier.SMALL,
        input_cost_per_1m_tokens=0.15,
        output_cost_per_1m_tokens=0.60,
        context_window=128000,
        capabilities=["general", "coding", "summarization", "extraction"],
        supports_vision=True,
        supports_tools=True,
        enabled=True,
        avg_latency_ms=450,
        quality_score=0.82,
    ),
    ModelMetadata(
        id="gpt-4o",
        name="GPT-4o",
        provider="openai",
        type=ModelType.API,
        tier=ModelTier.MEDIUM,
        input_cost_per_1m_tokens=2.50,
        output_cost_per_1m_tokens=10.00,
        context_window=128000,
        capabilities=["general", "coding", "reasoning", "summarization"],
        supports_vision=True,
        supports_tools=True,
        enabled=True,
        avg_latency_ms=900,
        quality_score=0.92,
    ),
    ModelMetadata(
        id="gpt-4-turbo",
        name="GPT-4 Turbo",
        provider="openai",
        type=ModelType.API,
        tier=ModelTier.STRONG,
        input_cost_per_1m_tokens=10.00,
        output_cost_per_1m_tokens=30.00,
        context_window=128000,
        capabilities=["general", "coding", "reasoning", "creative_writing"],
        supports_vision=True,
        supports_tools=True,
        enabled=True,
        avg_latency_ms=1400,
        quality_score=0.96,
    ),
    ModelMetadata(
        id="claude-3-haiku",
        name="Claude 3 Haiku",
        provider="anthropic",
        type=ModelType.API,
        tier=ModelTier.SMALL,
        input_cost_per_1m_tokens=0.25,
        output_cost_per_1m_tokens=1.25,
        context_window=200000,
        capabilities=["general", "summarization", "extraction", "classification"],
        supports_vision=True,
        supports_tools=True,
        enabled=False,
        avg_latency_ms=400,
        quality_score=0.80,
    ),
    ModelMetadata(
        id="claude-3-5-sonnet",
        name="Claude 3.5 Sonnet",
        provider="anthropic",
        type=ModelType.API,
        tier=ModelTier.MEDIUM,
        input_cost_per_1m_tokens=3.00,
        output_cost_per_1m_tokens=15.00,
        context_window=200000,
        capabilities=["general", "coding", "reasoning", "creative_writing"],
        supports_vision=True,
        supports_tools=True,
        enabled=False,
        avg_latency_ms=950,
        quality_score=0.94,
    ),
    ModelMetadata(
        id="gemini-1.5-flash",
        name="Gemini 1.5 Flash",
        provider="google",
        type=ModelType.API,
        tier=ModelTier.SMALL,
        input_cost_per_1m_tokens=0.075,
        output_cost_per_1m_tokens=0.30,
        context_window=1000000,
        capabilities=["general", "summarization", "translation"],
        supports_vision=True,
        supports_tools=True,
        enabled=False,
        avg_latency_ms=380,
        quality_score=0.81,
    ),
    ModelMetadata(
        id="mock-echo",
        name="Mock Echo (Local)",
        provider="mock",
        type=ModelType.LOCAL,
        tier=ModelTier.SMALL,
        input_cost_per_1m_tokens=0.0,
        output_cost_per_1m_tokens=0.0,
        context_window=32000,
        capabilities=["general", "coding", "reasoning"],
        enabled=True,
        avg_latency_ms=50,
        quality_score=0.91,
    ),
    ModelMetadata(
        id="mock-echo-medium",
        name="Mock Echo Medium (Local)",
        provider="mock",
        type=ModelType.LOCAL,
        tier=ModelTier.MEDIUM,
        input_cost_per_1m_tokens=0.0,
        output_cost_per_1m_tokens=0.0,
        context_window=32000,
        capabilities=["general", "coding", "reasoning"],
        enabled=True,
        avg_latency_ms=75,
        quality_score=0.92,
    ),
    ModelMetadata(
        id="mock-echo-strong",
        name="Mock Echo Strong (Local)",
        provider="mock",
        type=ModelType.LOCAL,
        tier=ModelTier.STRONG,
        input_cost_per_1m_tokens=0.0,
        output_cost_per_1m_tokens=0.0,
        context_window=32000,
        capabilities=["general", "coding", "reasoning", "creative_writing"],
        enabled=True,
        avg_latency_ms=100,
        quality_score=0.96,
    ),
]


class ModelRegistry:
    """In-memory model registry with optional JSON persistence."""

    def __init__(self, settings: Settings | None = None, registry_path: Path | None = None) -> None:
        self.settings = settings or get_settings()
        self.registry_path = registry_path or Path("data/processed/model_registry.json")
        self._models: dict[str, ModelMetadata] = {}
        self._load_registry()

    def _load_registry(self) -> None:
        if self.registry_path.exists():
            try:
                raw = json.loads(self.registry_path.read_text(encoding="utf-8"))
                models = [ModelMetadata.model_validate(item) for item in raw]
                self._models = {model.id: model for model in models}
                self._merge_missing_defaults()
                logger.info("Loaded %d models from %s", len(self._models), self.registry_path)
                return
            except (json.JSONDecodeError, ValueError) as exc:
                logger.warning("Failed to load registry file, using defaults: %s", exc)

        self._models = {model.id: model for model in DEFAULT_MODELS}
        self._apply_tier_overrides()
        self._persist()

    def _merge_missing_defaults(self) -> None:
        updated = False
        for model in DEFAULT_MODELS:
            if model.id not in self._models:
                self._models[model.id] = model
                updated = True
        if updated:
            self._apply_tier_overrides()
            self._persist()

    def _apply_tier_overrides(self) -> None:
        tier_overrides = {
            ModelTier.SMALL: self.settings.small_model_id,
            ModelTier.MEDIUM: self.settings.medium_model_id,
            ModelTier.STRONG: self.settings.strong_model_id,
        }
        for tier, model_id in tier_overrides.items():
            if model_id and model_id in self._models:
                for model in self._models.values():
                    if model.tier == tier and model.id != model_id:
                        model.enabled = False
                self._models[model_id].enabled = True

    def _persist(self) -> None:
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        payload = [model.model_dump(mode="json") for model in self._models.values()]
        self.registry_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def list_models(self, enabled_only: bool = False) -> list[ModelMetadata]:
        models = list(self._models.values())
        if enabled_only:
            models = [model for model in models if model.enabled]
        return sorted(models, key=lambda m: (m.tier.value, m.name))

    def get_model(self, model_id: str) -> ModelMetadata | None:
        return self._models.get(model_id)

    def get_models_by_tier(self, tier: ModelTier, enabled_only: bool = True) -> list[ModelMetadata]:
        models = [m for m in self._models.values() if m.tier == tier]
        if enabled_only:
            models = [m for m in models if m.enabled]
        return sorted(models, key=lambda m: m.input_cost_per_1m_tokens)

    def get_primary_model_for_tier(self, tier: ModelTier) -> ModelMetadata | None:
        """Return the cheapest enabled model for a given tier."""
        models = self.get_models_by_tier(tier, enabled_only=True)
        return models[0] if models else None

    def add_model(self, request: ModelCreateRequest) -> ModelMetadata:
        if request.id in self._models:
            raise ValueError(f"Model with id '{request.id}' already exists")
        model = ModelMetadata.model_validate(request.model_dump())
        self._models[model.id] = model
        self._persist()
        return model

    def update_model(self, model_id: str, request: ModelUpdateRequest) -> ModelMetadata:
        model = self._models.get(model_id)
        if not model:
            raise KeyError(f"Model '{model_id}' not found")
        updates = request.model_dump(exclude_unset=True)
        updated = model.model_copy(update=updates)
        self._models[model_id] = updated
        self._persist()
        return updated

    def set_enabled(self, model_id: str, enabled: bool) -> ModelMetadata:
        return self.update_model(model_id, ModelUpdateRequest(enabled=enabled))

    def delete_model(self, model_id: str) -> None:
        if model_id not in self._models:
            raise KeyError(f"Model '{model_id}' not found")
        del self._models[model_id]
        self._persist()


_registry: ModelRegistry | None = None


def get_model_registry() -> ModelRegistry:
    global _registry
    if _registry is None:
        _registry = ModelRegistry()
    return _registry
