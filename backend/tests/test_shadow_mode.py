"""Shadow mode and embedding collection through the real chat flow (mock providers, no network)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config.settings import get_settings
from app.db import outcome_repository
from app.db.database import get_connection
from app.main import app
from app.models.registry import get_model_registry
from app.providers.mock import MockProvider
from app.schemas.chat import ChatMessage, ChatRequest
from app.schemas.models import ModelUpdateRequest
from app.services.chat import ChatService

CHEAP, MID, STRONG = "mock-echo", "mock-echo-medium", "mock-echo-strong"
PROMPT = "Explain how a hash table handles collisions using chaining."
client = TestClient(app)


def set_env(monkeypatch, **values):
    for key, value in values.items():
        monkeypatch.setenv(key, str(value))
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def env(monkeypatch):
    set_env(
        monkeypatch,
        APP_ENV="development",
        ROUTER_TYPE="rule_based",
        EMBEDDING_MODEL="hashing",
        EVALUATE_ON_CHAT="false",
        QUALITY_FLOOR="0.80",
        LEARNED_MIN_SAMPLES="5",
        SHADOW_ROUTER_ENABLED="false",
        COLLECT_EMBEDDINGS="false",
    )
    registry = get_model_registry()
    for model in registry.list_models():
        registry.set_enabled(model.id, model.provider == "mock")
    for model_id, (cin, cout) in {CHEAP: (0.1, 0.4), MID: (1.0, 4.0), STRONG: (5.0, 20.0)}.items():
        registry.update_model(model_id, ModelUpdateRequest(input_cost_per_1m_tokens=cin, output_cost_per_1m_tokens=cout))


def chat(model: str = "auto", **extra) -> ChatRequest:
    return ChatRequest(model=model, messages=[ChatMessage(role="user", content=PROMPT)], **extra)


def shadow_rows() -> list[dict]:
    with get_connection() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM shadow_decisions ORDER BY id")]


# --- Embedding collection ----------------------------------------------------------------------------


async def test_nothing_about_the_prompt_is_stored_by_default():
    await ChatService().chat(chat(request_id="off-1"))
    assert all(row["embedding"] is None for row in outcome_repository.list_outcomes("off-1"))


async def test_collection_stores_an_embedding_never_the_text(monkeypatch):
    set_env(monkeypatch, COLLECT_EMBEDDINGS="true")
    await ChatService().chat(chat(request_id="on-1"))
    rows = outcome_repository.list_outcomes("on-1")
    assert rows and all(len(row["embedding"]) == 384 * 4 for row in rows)
    assert all(PROMPT.encode() not in bytes(row["embedding"]) for row in rows)


async def test_learned_router_collects_and_then_learns_from_its_own_traffic(monkeypatch):
    set_env(monkeypatch, ROUTER_TYPE="learned", EVALUATE_ON_CHAT="true", JUDGE_PROVIDER="mock")
    for i in range(6):
        await ChatService().chat(chat(request_id=f"learn-{i}"))
    with get_connection() as conn:
        judged = conn.execute(
            "SELECT COUNT(*) FROM model_outcomes WHERE embedding IS NOT NULL AND quality_score IS NOT NULL"
        ).fetchone()[0]
    assert judged >= 5  # the deployment now has enough data to leave the fallback
    from app.router.learned import LearnedRouter
    from app.schemas.routing import RouteRequest

    assert LearnedRouter().route(RouteRequest(prompt=PROMPT)).features["router_type"] == "learned"


# --- Shadow mode ---------------------------------------------------------------------------------------


async def test_shadow_off_records_nothing():
    await ChatService().chat(chat(CHEAP, request_id="s-off"))
    assert shadow_rows() == []


async def test_shadow_logs_the_would_be_choice_without_changing_the_request(monkeypatch):
    set_env(monkeypatch, SHADOW_ROUTER_ENABLED="true")
    calls: list[str] = []
    original = MockProvider.generate

    async def counting(self, request):
        calls.append(self.model.id)
        return await original(self, request)

    monkeypatch.setattr(MockProvider, "generate", counting)

    response = await ChatService().chat(chat(STRONG, request_id="s-1"))

    assert response.model == STRONG and response.routed is False  # served exactly as requested
    assert calls == [STRONG]  # shadow mode made no provider call of its own
    [row] = shadow_rows()
    assert row["request_id"] == "s-1" and row["served_by"] == "pinned"
    assert row["actual_model"] == STRONG
    assert row["shadow_model"] in {CHEAP, MID, STRONG}
    assert row["shadow_mode"] == "learned:fallback"  # cold start: no learned data yet
    assert row["agrees"] == (1 if row["shadow_model"] == STRONG else 0)
    assert row["shadow_estimated_cost"] >= 0


async def test_shadow_also_shadows_routed_requests(monkeypatch):
    set_env(monkeypatch, SHADOW_ROUTER_ENABLED="true")
    await ChatService().chat(chat("auto", request_id="s-2"))
    [row] = shadow_rows()
    assert row["served_by"] == "router"


async def test_a_shadow_failure_never_fails_or_changes_the_request(monkeypatch):
    set_env(monkeypatch, SHADOW_ROUTER_ENABLED="true")

    def boom(_router_type):
        raise RuntimeError("shadow exploded")

    monkeypatch.setattr("app.services.chat.create_router", boom)
    response = await ChatService().chat(chat(MID, request_id="s-3"))
    assert response.model == MID
    assert shadow_rows() == []


def test_shadow_summary_and_segment_endpoints(monkeypatch):
    set_env(monkeypatch, SHADOW_ROUTER_ENABLED="true")
    empty = client.get("/api/shadow/summary").json()
    assert empty == {"requests": 0}

    for i, model in enumerate((CHEAP, STRONG, STRONG)):
        assert client.post(
            "/api/chat", json={"model": model, "messages": [{"role": "user", "content": PROMPT}], "request_id": f"sum-{i}"}
        ).status_code == 200

    summary = client.get("/api/shadow/summary").json()
    assert summary["requests"] == 3
    assert 0.0 <= summary["agreement_rate"] <= 1.0
    assert summary["mean_actual_cost"] is not None and summary["mean_shadow_estimated_cost"] is not None
    assert "predicted, never measured" in summary["note"]
    assert sum(summary["shadow_modes"].values()) == 3
    assert client.get("/api/shadow/summary", params={"limit": 1}).json()["requests"] == 1

    segments = client.get("/api/performance/segments").json()
    assert segments["quality_floor"] == 0.8 and "segments" in segments


def test_shadow_endpoints_require_the_api_key_when_configured(monkeypatch):
    set_env(monkeypatch, ROUTER_API_KEY="k")
    assert client.get("/api/shadow/summary").status_code == 401
    assert client.get("/api/shadow/summary", headers={"Authorization": "Bearer k"}).status_code == 200
