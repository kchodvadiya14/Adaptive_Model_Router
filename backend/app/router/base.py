"""Router interface and factory."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.config.settings import Settings, get_settings
from app.schemas.routing import RouteRequest, RoutingDecision


class Router(ABC):
    @abstractmethod
    def route(self, request: RouteRequest, configuration: dict[str, Any] | None = None) -> RoutingDecision:
        """Analyze a prompt and return a routing decision."""


def create_router(router_type: str, settings: Settings | None = None) -> Router:
    """Instantiate a router by type without relying on ROUTER_TYPE env."""
    settings = settings or get_settings()

    if router_type == "rule_based":
        from app.router.rule_based import RuleBasedRouter

        return RuleBasedRouter(settings=settings)

    if router_type == "tfidf":
        from app.router.tfidf_router import TFIDFRouter

        return TFIDFRouter(settings=settings)

    if router_type == "embedding":
        from app.router.embedding_router import EmbeddingRouter

        return EmbeddingRouter(settings=settings)

    if router_type == "bert":
        from app.router.bert_router import BERTRouter

        return BERTRouter(settings=settings)

    raise ValueError(f"Unsupported router type: {router_type}")


def get_router(settings: Settings | None = None) -> Router:
    settings = settings or get_settings()
    return create_router(settings.router_type, settings=settings)
