"""Embedding ML router."""

from app.router.ml_base import MLRouter
from app.schemas.training import RouterTrainType


class EmbeddingRouter(MLRouter):
    router_type = RouterTrainType.EMBEDDING
