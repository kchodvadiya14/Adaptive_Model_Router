"""USE_MOCK_PROVIDERS runs the whole gateway keylessly: every model is answered by the mock provider."""

from __future__ import annotations

from app.config.settings import get_settings
from app.models.registry import get_model_registry
from app.providers.base import GenerationRequest
from app.providers.factory import get_provider_for_model
from app.providers.mock import MockProvider
from app.schemas.chat import ChatMessage, ChatRequest
from app.services.chat import ChatService


def test_flag_off_keeps_real_adapters(monkeypatch):
    monkeypatch.setenv("USE_MOCK_PROVIDERS", "false")
    get_settings.cache_clear()
    model = get_model_registry().get_model("gpt-4o-mini")  # an OpenAI-provider model in the test registry
    assert not isinstance(get_provider_for_model(model), MockProvider)


def test_flag_on_answers_any_model_with_the_mock(monkeypatch):
    monkeypatch.setenv("USE_MOCK_PROVIDERS", "true")
    get_settings.cache_clear()
    model = get_model_registry().get_model("gpt-4o-mini")
    assert isinstance(get_provider_for_model(model), MockProvider)


async def test_stronger_tiers_write_fuller_mock_answers():
    registry = get_model_registry()
    lengths = {}
    for model_id in ("mock-echo", "mock-echo-medium", "mock-echo-strong"):
        provider = MockProvider(registry.get_model(model_id))
        result = await provider.generate(GenerationRequest(messages=[{"role": "user", "content": "Explain hashing."}]))
        lengths[model_id] = len(result.content)
        assert result.content.startswith(f"[Mock {registry.get_model(model_id).name}]")
    assert lengths["mock-echo"] < lengths["mock-echo-medium"] < lengths["mock-echo-strong"]


async def test_a_keyless_registry_model_completes_a_chat(monkeypatch):
    monkeypatch.setenv("USE_MOCK_PROVIDERS", "true")
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("EVALUATE_ON_CHAT", "false")
    get_settings.cache_clear()
    response = await ChatService().chat(
        ChatRequest(model="gpt-4o-mini", messages=[ChatMessage(role="user", content="Say hi")])
    )
    assert response.model == "gpt-4o-mini" and response.content.startswith("[Mock")
