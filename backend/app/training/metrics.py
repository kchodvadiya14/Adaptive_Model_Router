"""Training evaluation metrics for ML routers."""

from __future__ import annotations

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)

from app.schemas.training import ConfusionMatrix, TrainingMetrics


def evaluate_classifier(y_true: np.ndarray, y_pred: np.ndarray, y_prob: np.ndarray | None = None) -> TrainingMetrics:
    cm = confusion_matrix(y_true, y_pred, labels=[0, 1])
    return TrainingMetrics(
        train_accuracy=0.0,
        validation_accuracy=float(accuracy_score(y_true, y_pred)),
        test_accuracy=float(accuracy_score(y_true, y_pred)),
        precision=float(precision_score(y_true, y_pred, zero_division=0)),
        recall=float(recall_score(y_true, y_pred, zero_division=0)),
        f1=float(f1_score(y_true, y_pred, zero_division=0)),
        routing_threshold=0.0,
        confusion_matrix=ConfusionMatrix(
            true_negative=int(cm[0, 0]) if cm.shape == (2, 2) else 0,
            false_positive=int(cm[0, 1]) if cm.shape == (2, 2) else 0,
            false_negative=int(cm[1, 0]) if cm.shape == (2, 2) else 0,
            true_positive=int(cm[1, 1]) if cm.shape == (2, 2) else 0,
        ),
        probability_mean=float(np.mean(y_prob)) if y_prob is not None else None,
    )


def merge_split_metrics(train_m: TrainingMetrics, val_m: TrainingMetrics, test_m: TrainingMetrics, threshold: float) -> TrainingMetrics:
    return TrainingMetrics(
        train_accuracy=train_m.validation_accuracy,
        validation_accuracy=val_m.validation_accuracy,
        test_accuracy=test_m.test_accuracy,
        precision=test_m.precision,
        recall=test_m.recall,
        f1=test_m.f1,
        routing_threshold=threshold,
        confusion_matrix=test_m.confusion_matrix,
        probability_mean=test_m.probability_mean,
    )
