"""Pydantic schemas for scoped usage reporting."""

from pydantic import BaseModel, Field


class UsageFilters(BaseModel):
    user_id: str | None = None
    session_id: str | None = None
    model_id: str | None = None
    tag_key: str | None = None
    tag_value: str | None = None


class UsageBreakdownEntry(BaseModel):
    key: str
    total_requests: int
    successful_requests: int
    fallback_requests: int
    total_estimated_cost: float
    average_latency_ms: float


class UsageSummary(BaseModel):
    filters: UsageFilters
    total_requests: int
    successful_requests: int
    fallback_requests: int
    total_estimated_cost: float = Field(
        description="Sum of per-request cost computed from token usage and registry pricing — "
        "an estimate, not a provider bill.",
    )
    average_latency_ms: float
    by_user: list[UsageBreakdownEntry] = Field(default_factory=list)
    by_model: list[UsageBreakdownEntry] = Field(default_factory=list)
    by_tag: list[UsageBreakdownEntry] = Field(
        default_factory=list,
        description="One entry per 'key=value' tag; a request with several tags counts toward each.",
    )
