"""BERT-style classifier using deep MLP on sentence embeddings."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import numpy as np
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from app.config.settings import get_settings
from app.schemas.training import RouterTrainType, TrainedModelInfo
from app.training.data import load_training_split
from app.training.metrics import evaluate_classifier, merge_split_metrics
from app.training.registry import register_model, save_artifact
from app.training.train_embedding import EmbeddingVectorizer


def train_bert_router(dataset_id: str, routing_threshold: float | None = None) -> TrainedModelInfo:
    """Train a deeper classifier on embeddings as a BERT-style advanced router."""
    settings = get_settings()
    threshold = routing_threshold if routing_threshold is not None else settings.routing_threshold
    split = load_training_split(dataset_id)

    pipeline = Pipeline(
        [
            ("embed", EmbeddingVectorizer()),
            ("scale", StandardScaler(with_mean=False)),
            (
                "clf",
                MLPClassifier(
                    hidden_layer_sizes=(256, 128, 64),
                    activation="relu",
                    max_iter=400,
                    random_state=42,
                ),
            ),
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
        "router_type": RouterTrainType.BERT.value,
        "pipeline": pipeline,
        "threshold": threshold,
        "dataset_id": dataset_id,
        "backend": "mlp-on-sentence-embeddings",
    }
    path = save_artifact(model_id, RouterTrainType.BERT, payload)
    info = TrainedModelInfo(
        id=model_id,
        router_type=RouterTrainType.BERT,
        dataset_id=dataset_id,
        model_path=str(path),
        created_at=datetime.now(UTC).isoformat(),
        metrics=metrics,
        threshold=threshold,
        samples=len(split.texts),
    )
    return register_model(info)
