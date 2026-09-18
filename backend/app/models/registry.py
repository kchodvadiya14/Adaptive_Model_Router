"""Central model registry for discovering and managing LLM metadata."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from app.config.settings import Settings, get_settings
from app.schemas.models import ModelCreateRequest, ModelMetadata, ModelTier, ModelType, ModelUpdateRequest

logger = logging.getLogger(__name__)

# Production lineup of free-tier models from Groq, Google and OpenRouter. Costs are the
# providers' published paid list prices (Sept 2026), so cost and savings figures show what the
# traffic would cost on a paid plan. Each tier routes to its cheapest enabled model.
DEFAULT_MODELS: list[ModelMetadata] = [
    ModelMetadata(
        id="openai/gpt-oss-20b",
        name="GPT-OSS 20B (Groq)",
        provider="groq",
        type=ModelType.API,
        tier=ModelTier.SMALL,
        input_cost_per_1m_tokens=0.075,
        output_cost_per_1m_tokens=0.3,
        context_window=131072,
        capabilities=["general", "coding", "summarization"],
        supports_vision=False,
        supports_tools=True,
        enabled=True,
        avg_latency_ms=1200,
        quality_score=0.82,
    ),
    # Pinned use only: pricier than the tier primary, and the free OpenRouter key allows 50 requests/day.
    ModelMetadata(
        id="nvidia/nemotron-3-super-120b-a12b:free",
        name="Nemotron 3 Super 120B (OpenRouter)",
        provider="openai_compatible",
        type=ModelType.API,
        tier=ModelTier.SMALL,
        input_cost_per_1m_tokens=0.08,
        output_cost_per_1m_tokens=0.45,
        context_window=262144,
        capabilities=["general", "coding", "reasoning", "summarization"],
        supports_vision=False,
        supports_tools=False,
        enabled=True,
        avg_latency_ms=11000,
        quality_score=0.86,
    ),
    # Also the default quality judge (JUDGE_MODEL_ID).
    ModelMetadata(
        id="openai/gpt-oss-120b",
        name="GPT-OSS 120B (Groq)",
        provider="groq",
        type=ModelType.API,
        tier=ModelTier.MEDIUM,
        input_cost_per_1m_tokens=0.15,
        output_cost_per_1m_tokens=0.6,
        context_window=131072,
        capabilities=["general", "coding", "reasoning", "summarization"],
        supports_vision=False,
        supports_tools=True,
        enabled=True,
        avg_latency_ms=1500,
        quality_score=0.88,
    ),
    ModelMetadata(
        id="gemini-3.5-flash-lite",
        name="Gemini 3.5 Flash-Lite",
        provider="google",
        type=ModelType.API,
        tier=ModelTier.STRONG,
        input_cost_per_1m_tokens=0.3,
        output_cost_per_1m_tokens=2.5,
        context_window=1000000,
        capabilities=["general", "coding", "reasoning", "summarization", "translation"],
        supports_vision=False,
        supports_tools=False,
        enabled=True,
        avg_latency_ms=3000,
        quality_score=0.92,
    ),
    # Pinned use only: the free tier allows about 20 requests/day.
    ModelMetadata(
        id="gemini-3.5-flash",
        name="Gemini 3.5 Flash",
        provider="google",
        type=ModelType.API,
        tier=ModelTier.STRONG,
        input_cost_per_1m_tokens=1.5,
        output_cost_per_1m_tokens=9.0,
        context_window=1000000,
        capabilities=["general", "coding", "reasoning", "creative_writing"],
        supports_vision=False,
        supports_tools=False,
        enabled=True,
        avg_latency_ms=10000,
        quality_score=0.95,
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
