"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import verify_router_api_key
from app.api.benchmark import benchmark_router, reports_router
from app.api.dataset import router as dataset_router
from app.api.chat import router as chat_router
from app.api.evaluation import router as evaluation_router
from app.api.metrics import router as metrics_router
from app.api.models import router as models_router
from app.api.routing import router as routing_router
from app.api.experiments import router as experiments_router
from app.api.model_health import router as model_health_router
from app.api.openai_compat import router as openai_compat_router
from app.api.performance import router as performance_router
from app.api.training import router as training_router
from app.api.usage import router as usage_router
from app.config.settings import get_settings
from app.db.database import init_db
from app.schemas.models import HealthResponse
from app.utils.logging import setup_logging

APP_VERSION = "1.0.0"


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    init_db()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=APP_VERSION,
        description="Adaptive Model Router — automatically selects the most cost-effective LLM for each query.",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Every native /api/* route requires the bearer key when ROUTER_API_KEY is set. The
    # /v1 router declares the same dependency itself; /health stays open for probes.
    protected = [Depends(verify_router_api_key)]
    for api_router in (
        chat_router,
        evaluation_router,
        dataset_router,
        benchmark_router,
        reports_router,
        metrics_router,
        models_router,
        training_router,
        routing_router,
        experiments_router,
        model_health_router,
        usage_router,
        performance_router,
    ):
        app.include_router(api_router, dependencies=protected)
    app.include_router(openai_compat_router)

    @app.get("/health", response_model=HealthResponse, tags=["health"])
    def health_check() -> HealthResponse:
        return HealthResponse(
            status="ok",
            app_name=settings.app_name,
            version=APP_VERSION,
            environment=settings.app_env,
        )

    return app


app = create_app()
