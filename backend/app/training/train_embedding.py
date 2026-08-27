"""Sentence embedding + classifier router training."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from app.config.settings import get_settings
from app.schemas.training import RouterTrainType, TrainedModelInfo
from app.training.data import load_training_split
from app.training.metrics import evaluate_classifier, merge_split_metrics
from app.training.registry import register_model, save_artifact

EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"


class EmbeddingVectorizer:
    """Wrap sentence-transformers for sklearn-compatible training."""

    def __init__(self, model_name: str = EMBEDDING_MODEL_NAME) -> None:
        self.model_name = model_name
        self._model = None

    def _load(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
        return self._model

    def fit(self, texts, y=None):  # noqa: ARG002
        self._load()
        return self

    def transform(self, texts: list[str]) -> np.ndarray:
        model = self._load()
        return np.array(model.encode(texts, show_progress_bar=False))

    def fit_transform(self, texts, y=None) -> np.ndarray:
        self.fit(texts, y)
        return self.transform(texts)


def train_embedding_router(dataset_id: str, routing_threshold: float | None = None) -> TrainedModelInfo:
    settings = get_settings()
    threshold = routing_threshold if routing_threshold is not None else settings.routing_threshold
    split = load_training_split(dataset_id)

    pipeline = Pipeline(
        [
            ("embed", EmbeddingVectorizer()),
            ("scale", StandardScaler(with_mean=False)),
            ("clf", LogisticRegression(max_iter=1000, class_weight="balanced")),
        ]
    )
    pipeline.fit(split.train_texts, split.y_train)

    def _eval(texts: list[str], labels: np.ndarray):
        preds = pipeline.predict(texts)
        probs = pipeline.predict_proba(texts)[:, 1]
        return evaluate_classifier(labels, preds, probs)

    train_metrics = _eval(split.train_texts, split.y_train)
    val_metrics = _eval(split.val_texts, split.y_val)
    test_metrics = _eval(split.test_texts, split.y_test)
    metrics = merge_split_metrics(train_metrics, val_metrics, test_metrics, threshold)

    model_id = str(uuid.uuid4())
    payload = {
        "router_type": RouterTrainType.EMBEDDING.value,
        "pipeline": pipeline,
        "threshold": threshold,
        "dataset_id": dataset_id,
        "embedding_model": EMBEDDING_MODEL_NAME,
    }
    path = save_artifact(model_id, RouterTrainType.EMBEDDING, payload)
    info = TrainedModelInfo(
        id=model_id,
        router_type=RouterTrainType.EMBEDDING,
        dataset_id=dataset_id,
        model_path=str(path),
        created_at=datetime.now(UTC).isoformat(),
        metrics=metrics,
        threshold=threshold,
        samples=len(split.texts),
    )
    return register_model(info)
