"""Preference dataset generation pipeline."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.datasets.json_dataset import JsonDatasetAdapter
from app.datasets.storage import add_manifest, save_records
from app.evaluation.judge import get_judge
from app.models.registry import get_model_registry
from app.providers.base import GenerationRequest
from app.providers.factory import get_provider_for_model
from app.router.base import get_router
from app.schemas.dataset import DatasetManifest, PreferenceRecord
from app.schemas.evaluation import JudgeScore
from app.schemas.models import ModelTier
from app.schemas.routing import RouteRequest


def compute_preference_labels(
    small_score: float,
    medium_score: float,
    strong_score: float,
    quality_floor: float,
) -> tuple[str, bool, bool, bool]:
    scores = {"small": small_score, "medium": medium_score, "strong": strong_score}
    sufficient = {tier: score >= quality_floor for tier, score in scores.items()}

    preferred = "strong"
    for tier in ("small", "medium", "strong"):
        if sufficient[tier]:
            preferred = tier
            break

    return preferred, sufficient["small"], sufficient["medium"], sufficient["strong"]


class PreferenceDatasetGenerator:
    async def generate(
        self,
        *,
        source_path: str,
        name: str,
        quality_floor: float,
        max_prompts: int,
        description: str = "",
    ) -> DatasetManifest:
        adapter = JsonDatasetAdapter(source_path)
        prompts = adapter.load()[:max_prompts]
        registry = get_model_registry()
        judge = get_judge()
        router = get_router()

        small_model = registry.get_primary_model_for_tier(ModelTier.SMALL)
        medium_model = registry.get_primary_model_for_tier(ModelTier.MEDIUM)
        strong_model = registry.get_primary_model_for_tier(ModelTier.STRONG)
        if not small_model or not medium_model or not strong_model:
            raise ValueError("Small, medium, and strong tier models must be enabled.")

        dataset_id = str(uuid.uuid4())
        records: list[PreferenceRecord] = []

        for item in prompts:
            routing = router.route(
                RouteRequest(prompt=item.prompt),
                configuration={"quality_floor": quality_floor},
            )
            tier_responses: dict[str, tuple[str, JudgeScore]] = {}
            for tier, model in (
                ("small", small_model),
                ("medium", medium_model),
                ("strong", strong_model),
            ):
                provider = get_provider_for_model(model)
                generation = await provider.generate(
                    GenerationRequest(messages=[{"role": "user", "content": item.prompt}], max_tokens=512)
                )
                score = await judge.evaluate(item.prompt, generation.content)
                tier_responses[tier] = (generation.content, score)

            small_score = tier_responses["small"][1].overall
            medium_score = tier_responses["medium"][1].overall
            strong_score = tier_responses["strong"][1].overall
            preferred, small_ok, medium_ok, strong_ok = compute_preference_labels(
                small_score, medium_score, strong_score, quality_floor
            )

            records.append(
                PreferenceRecord(
                    id=item.id,
                    prompt=item.prompt,
                    task_type=routing.task_type,
                    difficulty=routing.difficulty,
                    small_model_id=small_model.id,
                    medium_model_id=medium_model.id,
                    strong_model_id=strong_model.id,
                    small_response=tier_responses["small"][0],
                    medium_response=tier_responses["medium"][0],
                    strong_response=tier_responses["strong"][0],
                    small_score=small_score,
                    medium_score=medium_score,
                    strong_score=strong_score,
                    small_judge=tier_responses["small"][1],
                    medium_judge=tier_responses["medium"][1],
                    strong_judge=tier_responses["strong"][1],
                    preferred_model=preferred,  # type: ignore[arg-type]
                    small_sufficient=small_ok,
                    medium_sufficient=medium_ok,
                    strong_sufficient=strong_ok,
                    quality_floor=quality_floor,
                    evaluation_source="judge",
                    metadata={"category": item.category, "prompt_id": item.id},
                )
            )

        output_path = save_records(dataset_id, records)
        manifest = DatasetManifest(
            id=dataset_id,
            name=name,
            created_at=datetime.now(UTC).isoformat(),
            source_path=source_path,
            output_path=str(output_path),
            quality_floor=quality_floor,
            record_count=len(records),
            judge_provider=judge.__class__.__name__.replace("Judge", "").lower() or "mock",
            description=description,
        )
        add_manifest(manifest)
        return manifest


_generator: PreferenceDatasetGenerator | None = None


def get_dataset_generator() -> PreferenceDatasetGenerator:
    global _generator
    if _generator is None:
        _generator = PreferenceDatasetGenerator()
    return _generator
