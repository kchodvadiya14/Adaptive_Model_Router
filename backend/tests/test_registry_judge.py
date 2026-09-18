import pytest

from app.config.settings import get_settings
from app.evaluation.judge import MockJudge, RegistryJudge, _extract_json, get_judge
from app.providers.base import GenerationResponse, ProviderError


class _StubProvider:
    def __init__(self, content: str) -> None:
        self.content = content
        self.requests = []

    async def generate(self, request):
        self.requests.append(request)
        return GenerationResponse(content=self.content, input_tokens=10, output_tokens=10, latency_ms=5.0)


@pytest.fixture
def registry_judge_settings(monkeypatch):
    monkeypatch.setenv("JUDGE_PROVIDER", "registry")
    monkeypatch.setenv("JUDGE_MODEL_ID", "mock-echo")
    get_settings.cache_clear()
    yield get_settings()
    get_settings.cache_clear()


def _patch_provider(monkeypatch, content: str) -> _StubProvider:
    stub = _StubProvider(content)
    monkeypatch.setattr("app.providers.factory.get_provider_for_model", lambda model: stub)
    return stub


def test_get_judge_returns_registry_judge(registry_judge_settings):
    assert isinstance(get_judge(registry_judge_settings), RegistryJudge)


def test_get_judge_defaults_to_mock():
    assert isinstance(get_judge(), MockJudge)


async def test_registry_judge_scores_from_model_reply(monkeypatch, registry_judge_settings):
    reply = (
        "Here is my evaluation:\n```json\n"
        '{"correctness": 0.9, "relevance": 0.8, "completeness": 0.7, "reasoning_quality": 0.6, '
        '"instruction_following": 1.0, "overall": 0.85, "judge_reasoning": "Accurate."}\n```'
    )
    stub = _patch_provider(monkeypatch, reply)

    score = await get_judge(registry_judge_settings).evaluate("What is 2+2?", "4")

    assert score.overall == 0.85
    assert score.correctness == 0.9
    assert score.judge_provider == "registry:mock-echo"
    assert stub.requests[0].temperature == 0.0
    assert stub.requests[0].messages[0]["role"] == "system"


async def test_registry_judge_compare(monkeypatch, registry_judge_settings):
    _patch_provider(monkeypatch, '{"winner": "small", "confidence": 0.7, "reason": "Shorter and correct."}')

    result = await get_judge(registry_judge_settings).compare("q", "a", "b", "small", "strong")

    assert result.winner == "small"
    assert result.judge_provider == "registry:mock-echo"


async def test_registry_judge_unknown_model_raises(monkeypatch):
    monkeypatch.setenv("JUDGE_PROVIDER", "registry")
    monkeypatch.setenv("JUDGE_MODEL_ID", "no-such-model")
    get_settings.cache_clear()
    with pytest.raises(ProviderError):
        await get_judge().evaluate("q", "a")
    get_settings.cache_clear()


def test_extract_json_rejects_non_json():
    with pytest.raises(ProviderError):
        _extract_json("I think the answer is good.")
