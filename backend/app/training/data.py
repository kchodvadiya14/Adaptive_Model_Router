"""Training data utilities for ML routers."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sklearn.model_selection import train_test_split

from app.datasets.storage import load_records
from app.schemas.dataset import PreferenceRecord


@dataclass
class TrainingSplit:
    texts: list[str]
    labels: np.ndarray
    train_texts: list[str]
    val_texts: list[str]
    test_texts: list[str]
    y_train: np.ndarray
    y_val: np.ndarray
    y_test: np.ndarray


def strong_better_label(record: PreferenceRecord, margin: float = 0.03) -> int:
    """Return 1 when the strong model meaningfully outperforms cheaper tiers."""
    best_cheap = max(record.small_score, record.medium_score)
    return int(record.strong_score >= best_cheap + margin)


def _split_count(n_samples: int, fraction: float) -> int:
    """Return number of samples for a fractional split, keeping at least one train sample."""
    if fraction <= 0 or n_samples <= 1:
        return 0
    count = int(round(n_samples * fraction))
    return max(1, min(count, n_samples - 1))


def _stratify_if_possible(labels: np.ndarray, split_count: int) -> np.ndarray | None:
    """Use stratified splitting only when both partitions can hold every class."""
    labels = np.asarray(labels)
    classes = np.unique(labels)
    if len(classes) < 2:
        return None

    remain_count = len(labels) - split_count
    if split_count < len(classes) or remain_count < len(classes):
        return None

    _, class_counts = np.unique(labels, return_counts=True)
    if np.min(class_counts) < 2:
        return None

    return labels


def load_training_split(dataset_id: str, test_size: float = 0.2, val_size: float = 0.1) -> TrainingSplit:
    records = load_records(dataset_id)
    if len(records) < 4:
        raise ValueError("Need at least 4 preference records to train a router.")

    texts = [record.prompt for record in records]
    labels = np.array([strong_better_label(record) for record in records], dtype=np.int64)

    test_count = _split_count(len(texts), test_size)
    train_texts, test_texts, y_train, y_test = train_test_split(
        texts,
        labels,
        test_size=test_count,
        random_state=42,
        stratify=_stratify_if_possible(labels, test_count),
    )

    val_count = _split_count(len(train_texts), val_size)
    if val_count == 0 or len(train_texts) < 3:
        val_texts: list[str] = []
        y_val = np.array([], dtype=np.int64)
    else:
        train_texts, val_texts, y_train, y_val = train_test_split(
            train_texts,
            y_train,
            test_size=val_count,
            random_state=42,
            stratify=_stratify_if_possible(y_train, val_count),
        )

    return TrainingSplit(
        texts=texts,
        labels=labels,
        train_texts=train_texts,
        val_texts=val_texts,
        test_texts=test_texts,
        y_train=y_train,
        y_val=y_val,
        y_test=y_test,
    )
