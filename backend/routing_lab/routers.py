"""Routers under test, all exposing `curve(...)`: per-prompt (cost, quality) at each dial setting.

- `KnnRouter`  per-model quality = mean score of the k most similar training prompts.
- `MlpRouter`  one multi-output MLP on the embedding predicts every model's score.
- `RuleRouter` the gateway's existing static router (keyword features + hand-set quality priors),
               with its tiers mapped onto real models, so it is measured on the same footing.

Learned routers pick argmax over models of  predicted_quality - lambda * predicted_cost / cost_ref.
lambda = 0 is "always the predicted-best model"; large lambda is "always the cheapest".
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sklearn.neighbors import NearestNeighbors
from sklearn.neural_network import MLPRegressor

LAMBDAS = np.concatenate([[0.0], np.geomspace(0.01, 30.0, 47)])


@dataclass
class Table:
    """Aligned per-prompt arrays. scores/cost/out_tokens are (n_prompts, n_models)."""

    emb: np.ndarray
    scores: np.ndarray
    cost: np.ndarray
    in_tokens: np.ndarray
    out_tokens: np.ndarray

    def take(self, idx: np.ndarray) -> "Table":
        return Table(self.emb[idx], self.scores[idx], self.cost[idx], self.in_tokens[idx], self.out_tokens[idx])


def expected_cost(in_tokens: np.ndarray, pred_out_tokens: np.ndarray, prices: np.ndarray) -> np.ndarray:
    """Input length is known before routing; output length is predicted. prices: (n_models, 2) $/1M."""
    return (in_tokens * prices[:, 0] + pred_out_tokens * prices[:, 1]) / 1e6


def select(pred_quality: np.ndarray, pred_cost: np.ndarray, cost_ref: float) -> np.ndarray:
    """(n_lambdas, n_prompts) chosen model index for every dial setting."""
    penalty = pred_cost / cost_ref
    return np.stack([np.argmax(pred_quality - lam * penalty, axis=1) for lam in LAMBDAS])


def realised(choice: np.ndarray, table: Table) -> tuple[np.ndarray, np.ndarray]:
    """Per-prompt realised (cost, quality), shape (n_prompts, n_lambdas)."""
    rows = np.arange(table.scores.shape[0])
    cost = np.stack([table.cost[rows, c] for c in choice], axis=1)
    quality = np.stack([table.scores[rows, c] for c in choice], axis=1)
    return cost, quality


class KnnRouter:
    name = "kNN"

    def __init__(self, k: int = 40) -> None:
        self.k = k

    def fit(self, train: Table) -> "KnnRouter":
        self.train = train
        self.index = NearestNeighbors(n_neighbors=self.k, metric="cosine", algorithm="brute").fit(train.emb)
        return self

    def predict(self, emb: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        _, neighbours = self.index.kneighbors(emb)
        quality = self.train.scores[neighbours].mean(axis=1)
        out_tokens = self.train.out_tokens[neighbours].mean(axis=1)
        return quality, out_tokens


class MlpRouter:
    name = "MLP"

    def __init__(self, hidden: tuple[int, ...] = (256, 128), seed: int = 0) -> None:
        self.model = MLPRegressor(
            hidden_layer_sizes=hidden,
            alpha=1e-3,
            early_stopping=True,
            validation_fraction=0.1,
            n_iter_no_change=8,
            max_iter=200,
            random_state=seed,
        )

    def fit(self, train: Table) -> "MlpRouter":
        n_models = train.scores.shape[1]
        # Predict quality and log output length for every model in one network.
        targets = np.hstack([train.scores, np.log1p(train.out_tokens)])
        self.model.fit(train.emb, targets)
        self.n_models = n_models
        return self

    def predict(self, emb: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        out = self.model.predict(emb)
        quality = np.clip(out[:, : self.n_models], 0.0, 1.0)
        return quality, np.expm1(out[:, self.n_models :]).clip(min=1.0)


# --- The gateway's static router -----------------------------------------------------------------


@dataclass
class RuleTier:
    """A tier of the existing rule-based router, mapped onto one real model."""

    tier: str  # "small" | "medium" | "strong"
    model_index: int
    quality_prior: float  # the gateway registry's hand-set quality_score for that tier


def rule_based_choices(prompts: list[str], tiers: list[RuleTier], floors: np.ndarray) -> np.ndarray:
    """What app.router.policy would pick, for each quality floor, cheapest-first.

    Uses the gateway's own feature extraction, task classifier, difficulty estimate and quality
    formula (prior + task boost - difficulty penalty); only the model behind each tier differs.
    Returns (n_floors, n_prompts) of model indices."""
    from app.router.difficulty import estimate_difficulty
    from app.router.features import extract_features
    from app.router.policy import _capability_boost, difficulty_penalty
    from app.router.task_classifier import classify_task
    from app.schemas.models import ModelMetadata, ModelTier, ModelType

    tier_enum = {"small": ModelTier.SMALL, "medium": ModelTier.MEDIUM, "strong": ModelTier.STRONG}
    stand_ins = {
        t.tier: ModelMetadata(
            id=t.tier, name=t.tier, provider="lab", type=ModelType.API, tier=tier_enum[t.tier],
            input_cost_per_1m_tokens=0, output_cost_per_1m_tokens=0, context_window=8192,
            capabilities=["general", "coding", "reasoning", "summarization"],
            quality_score=t.quality_prior,
        )
        for t in tiers
    }
    order = sorted(tiers, key=lambda t: ("small", "medium", "strong").index(t.tier))  # cheapest first
    expected = np.zeros((len(prompts), len(order)))
    for i, prompt in enumerate(prompts):
        features = extract_features(prompt)
        task, _ = classify_task(features)
        difficulty = estimate_difficulty(features, task)
        for j, t in enumerate(order):
            model = stand_ins[t.tier]
            q = model.quality_score + _capability_boost(task, model) - difficulty_penalty(model.tier, difficulty)
            expected[i, j] = min(max(q, 0.0), 1.0)

    chosen = np.zeros((len(floors), len(prompts)), dtype=int)
    for f, floor in enumerate(floors):
        ok = expected >= floor
        first = np.where(ok.any(axis=1), ok.argmax(axis=1), expected.argmax(axis=1))  # cheapest passing tier, else best
        chosen[f] = [order[j].model_index for j in first]
    return chosen
