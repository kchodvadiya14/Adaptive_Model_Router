"""Scoped usage reporting API."""

from fastapi import APIRouter, HTTPException, Query, status

from app.schemas.usage import UsageFilters, UsageSummary
from app.services.usage import get_usage_summary

router = APIRouter(prefix="/api/usage", tags=["usage"])


@router.get("", response_model=UsageSummary)
def get_usage(
    user_id: str | None = Query(default=None),
    session_id: str | None = Query(default=None),
    model_id: str | None = Query(default=None),
    tag_key: str | None = Query(default=None, description="Only requests carrying this tag key."),
    tag_value: str | None = Query(default=None, description="Requires tag_key; exact value match."),
) -> UsageSummary:
    """Usage totals plus per-user, per-model and per-tag breakdowns, optionally filtered."""
    if tag_value is not None and tag_key is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="tag_value requires tag_key.",
        )
    return get_usage_summary(
        UsageFilters(
            user_id=user_id,
            session_id=session_id,
            model_id=model_id,
            tag_key=tag_key,
            tag_value=tag_value,
        )
    )
