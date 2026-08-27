"""Unified ML router training service."""

from __future__ import annotations

from app.schemas.training import RouterTrainType, TrainedModelInfo
from app.training.train_bert import train_bert_router
from app.training.train_embedding import train_embedding_router
from app.training.train_tfidf import train_tfidf_router


class TrainingService:
    def train(
        self,
        dataset_id: str,
        router_type: RouterTrainType,
        routing_threshold: float | None = None,
    ) -> TrainedModelInfo:
        if router_type == RouterTrainType.TFIDF:
            return train_tfidf_router(dataset_id, routing_threshold)
        if router_type == RouterTrainType.EMBEDDING:
            return train_embedding_router(dataset_id, routing_threshold)
        if router_type == RouterTrainType.BERT:
            return train_bert_router(dataset_id, routing_threshold)
        raise ValueError(f"Unsupported router type: {router_type}")


_training_service: TrainingService | None = None


def get_training_service() -> TrainingService:
    global _training_service
    if _training_service is None:
        _training_service = TrainingService()
    return _training_service
