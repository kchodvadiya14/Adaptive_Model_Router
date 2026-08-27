"""BERT-style ML router."""

from app.router.ml_base import MLRouter
from app.schemas.training import RouterTrainType


class BERTRouter(MLRouter):
    router_type = RouterTrainType.BERT
