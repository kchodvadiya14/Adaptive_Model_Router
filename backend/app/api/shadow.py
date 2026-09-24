"""Shadow-mode comparison of learned-router choices against what was actually served."""

from fastapi import APIRouter, Query

from app.services.shadow import shadow_summary

router = APIRouter(prefix="/api/shadow", tags=["shadow"])


@router.get("/summary")
def get_shadow_summary(limit: int | None = Query(default=None, ge=1, description="Only the most recent N decisions.")) -> dict:
    """Agreement rate and estimated cost change between the learned router's would-be choices and the
    models actually used. Quality for the shadow choice is predicted, not measured."""
    return shadow_summary(limit)
