"""Application configuration loaded from environment variables."""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = Field(default="Adaptive Model Router", alias="APP_NAME")
    app_env: str = Field(default="development", alias="APP_ENV")
    debug: bool = Field(default=True, alias="DEBUG")

    backend_host: str = Field(default="0.0.0.0", alias="BACKEND_HOST")
    backend_port: int = Field(default=8000, alias="BACKEND_PORT")
    cors_origins: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173",
        alias="CORS_ORIGINS",
    )

    router_type: Literal["rule_based", "tfidf", "embedding", "bert", "learned"] = Field(
        default="rule_based",
        alias="ROUTER_TYPE",
    )
    routing_threshold: float = Field(default=0.60, alias="ROUTING_THRESHOLD")
    quality_floor: float = Field(default=0.90, alias="QUALITY_FLOOR")
    cost_priority: float = Field(default=0.7, alias="COST_PRIORITY")
    latency_priority: float = Field(default=0.3, alias="LATENCY_PRIORITY")

    # Learned router (ROUTER_TYPE=learned): per-model quality predicted from similar past prompts.
    embedding_model: str = Field(
        default="sentence-transformers/all-MiniLM-L12-v2",
        alias="EMBEDDING_MODEL",
        description="Prompt encoder for the learned router. 'hashing' is a dependency-free offline fallback.",
    )
    collect_embeddings: bool = Field(
        default=False,
        alias="COLLECT_EMBEDDINGS",
        description="Store each prompt's embedding (never its text) with judged outcomes so a learned router can be trained later. Always on when ROUTER_TYPE=learned.",
    )
    learned_k: int = Field(default=40, ge=1, alias="LEARNED_K")
    learned_prior_weight: float = Field(
        default=3.0, ge=0, alias="LEARNED_PRIOR_WEIGHT",
        description="How many perfectly similar judged samples it takes to outweigh the registry prior.",
    )
    learned_min_similarity: float = Field(
        default=0.5, ge=0, lt=1, alias="LEARNED_MIN_SIMILARITY",
        description="Cosine similarity below which a past prompt carries no weight.",
    )
    learned_min_samples: int = Field(
        default=50, ge=0, alias="LEARNED_MIN_SAMPLES",
        description="Judged, embedded outcomes a deployment needs before the learned router replaces the static fallback.",
    )
    guard_window: int = Field(default=50, ge=1, alias="GUARD_WINDOW", description="Recent answers per task type the quality guard looks at.")
    guard_min_samples: int = Field(default=20, ge=1, alias="GUARD_MIN_SAMPLES")
    guard_tolerance: float = Field(
        default=0.05, ge=0, alias="GUARD_TOLERANCE",
        description="How far recent judged quality may fall below the floor before a task segment stops being cost-optimised.",
    )
    shadow_router_enabled: bool = Field(
        default=False, alias="SHADOW_ROUTER_ENABLED",
        description="Also compute what the learned router would have chosen for every request and log it, without acting on it.",
    )
    exploration_bonus: float = Field(
        default=0.10, ge=0, alias="EXPLORATION_BONUS",
        description="Optimism given to models with little evidence for a kind of prompt, so cheap models keep being tried.",
    )

    fallback_enabled: bool = Field(default=True, alias="FALLBACK_ENABLED")
    max_fallback_attempts: int = Field(default=3, ge=1, le=5, alias="MAX_FALLBACK_ATTEMPTS")
    fallback_on_quality_below: float | None = Field(default=0.85, alias="FALLBACK_ON_QUALITY_BELOW")
    fallback_escalation: Literal["tier_up", "strong_only"] = Field(
        default="tier_up",
        alias="FALLBACK_ESCALATION",
    )

    store_prompts: bool = Field(default=False, alias="STORE_PROMPTS")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    database_url: str = Field(default="sqlite:///./data/router.db", alias="DATABASE_URL")

    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    google_api_key: str = Field(default="", alias="GOOGLE_API_KEY")
    openai_compatible_base_url: str = Field(default="", alias="OPENAI_COMPATIBLE_BASE_URL")
    openai_compatible_api_key: str = Field(default="", alias="OPENAI_COMPATIBLE_API_KEY")
    groq_api_key: str = Field(default="", alias="GROQ_API_KEY")

    small_model_id: str = Field(default="", alias="SMALL_MODEL_ID")
    medium_model_id: str = Field(default="", alias="MEDIUM_MODEL_ID")
    strong_model_id: str = Field(default="", alias="STRONG_MODEL_ID")

    provider_timeout: float = Field(default=60.0, alias="PROVIDER_TIMEOUT")
    use_mock_providers: bool = Field(default=False, alias="USE_MOCK_PROVIDERS")
    max_request_messages: int = Field(default=50, alias="MAX_REQUEST_MESSAGES")

    judge_provider: Literal["mock", "openai", "registry"] = Field(default="mock", alias="JUDGE_PROVIDER")
    judge_model_id: str = Field(default="gpt-4o-mini", alias="JUDGE_MODEL_ID")
    evaluate_on_chat: bool = Field(default=True, alias="EVALUATE_ON_CHAT")

    router_api_key: str = Field(
        default="",
        alias="ROUTER_API_KEY",
        description="Optional bearer token for /v1/* OpenAI-compatible endpoints.",
    )

    health_failure_threshold: int = Field(
        default=3,
        ge=1,
        alias="HEALTH_FAILURE_THRESHOLD",
        description="Consecutive retryable provider failures before a model's circuit opens.",
    )
    request_min_attempt_budget_ms: float = Field(
        default=10.0,
        ge=0,
        alias="REQUEST_MIN_ATTEMPT_BUDGET_MS",
        description="With timeout_ms set, don't start a generation/evaluation step with less than this much budget left.",
    )
    health_cooldown_seconds: float = Field(
        default=30.0,
        ge=0,
        alias="HEALTH_COOLDOWN_SECONDS",
        description="Seconds an open circuit waits before allowing one half-open trial request.",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
