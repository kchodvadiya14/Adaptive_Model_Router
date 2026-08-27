"""TF-IDF ML router."""

from app.router.ml_base import MLRouter
from app.schemas.training import RouterTrainType


class TFIDFRouter(MLRouter):
    router_type = RouterTrainType.TFIDF
