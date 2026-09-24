"""ROUTER_API_KEY protects every native /api/* route as well as /v1/*; /health stays open."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config.settings import get_settings
from app.main import app

client = TestClient(app)

PROTECTED = [
    ("get", "/api/models"),
    ("get", "/api/metrics"),
    ("get", "/api/usage"),
    ("get", "/api/router/status"),
    ("get", "/api/health/models"),
    ("post", "/api/route"),
    ("post", "/api/chat"),
]


@pytest.fixture
def api_key(monkeypatch):
    monkeypatch.setenv("ROUTER_API_KEY", "test-secret-key")
    get_settings.cache_clear()
    yield "test-secret-key"
    get_settings.cache_clear()


def call(method: str, path: str, **kwargs):
    if method == "post":
        kwargs["json"] = {}
    return getattr(client, method)(path, **kwargs)


@pytest.mark.parametrize(("method", "path"), PROTECTED)
def test_native_routes_reject_missing_key(api_key, method, path):
    assert call(method, path).status_code == 401


@pytest.mark.parametrize(("method", "path"), PROTECTED)
def test_native_routes_reject_wrong_key(api_key, method, path):
    response = call(method, path, headers={"Authorization": "Bearer nope"})
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_native_route_accepts_correct_key(api_key):
    response = client.get("/api/models", headers={"Authorization": f"Bearer {api_key}"})
    assert response.status_code == 200


def test_health_stays_open(api_key):
    assert client.get("/health").status_code == 200


def test_no_key_configured_leaves_api_open(monkeypatch):
    monkeypatch.setenv("ROUTER_API_KEY", "")
    get_settings.cache_clear()
    assert client.get("/api/models").status_code == 200
