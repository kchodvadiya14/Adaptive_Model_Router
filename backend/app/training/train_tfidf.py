"""TF-IDF + Logistic Regression router training."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from app.config.settings import get_settings
from app.schemas.training import RouterTrainType, TrainedModelInfo
from app.training.data import load_training_split
from app.training.metrics import evaluate_classifier, merge_split_metrics
from app.training.registry import register_model, save_artifact


def train_tfidf_router(dataset_id: str, routing_threshold: float | None = None) -> TrainedModelInfo:
    settings = get_settings()
    threshold = routing_threshold if routing_threshold is not None else settings.routing_threshold
    split = load_training_split(dataset_id)

    pipeline = Pipeline(
        [
            ("tfidf", TfidfVectorizer(max_features=5000, ngram_range=(1, 2), stop_words="english")),
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
        "router_type": RouterTrainType.TFIDF.value,
        "pipeline": pipeline,
        "threshold": threshold,
        "dataset_id": dataset_id,
    }
    path = save_artifact(model_id, RouterTrainType.TFIDF, payload)
    info = TrainedModelInfo(
        id=model_id,
        router_type=RouterTrainType.TFIDF,
        dataset_id=dataset_id,
        model_path=str(path),
        created_at=datetime.now(UTC).isoformat(),
        metrics=metrics,
        threshold=threshold,
        samples=len(split.texts),
    )
    return register_model(info)
