from __future__ import annotations

from types import SimpleNamespace

import httpx

from app.config import Settings
from app.services import provider as provider_module


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def post(self, *_args, **_kwargs):
        self.calls += 1
        return self.responses.pop(0)


def response(status: int, retry_after: str | None = None) -> httpx.Response:
    headers = {"Retry-After": retry_after} if retry_after is not None else {}
    return httpx.Response(status, headers=headers, request=httpx.Request("POST", "https://example.test"))


def test_generic_api_key_takes_precedence(monkeypatch):
    monkeypatch.setenv("KIVI_LLM_API_KEY", "generic-key")
    monkeypatch.setenv("OPENAI_API_KEY", "legacy-key")
    cfg = Settings()
    assert cfg.api_key == "generic-key"


def test_openai_key_remains_backward_compatible(monkeypatch):
    monkeypatch.delenv("KIVI_LLM_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "legacy-key")
    cfg = Settings()
    assert cfg.api_key == "legacy-key"


def test_retryable_503_is_retried(monkeypatch):
    monkeypatch.setattr(
        provider_module,
        "settings",
        SimpleNamespace(api_key="x", max_retries=2, retry_base_seconds=0.0),
    )
    p = provider_module.OpenAICompatibleProvider()
    client = FakeClient([response(503, "0"), response(200)])
    sleeps = []
    result = p._request_with_retry(client, "https://example.test", {}, sleep_fn=sleeps.append)
    assert result.status_code == 200
    assert client.calls == 2
    assert sleeps == [0.0]


def test_permanent_401_is_not_retried(monkeypatch):
    monkeypatch.setattr(
        provider_module,
        "settings",
        SimpleNamespace(api_key="x", max_retries=3, retry_base_seconds=0.0),
    )
    p = provider_module.OpenAICompatibleProvider()
    client = FakeClient([response(401), response(200)])
    result = p._request_with_retry(client, "https://example.test", {}, sleep_fn=lambda _x: None)
    assert result.status_code == 401
    assert client.calls == 1


def test_invalid_base_url_fails_fast(monkeypatch):
    monkeypatch.setattr(
        provider_module,
        "settings",
        SimpleNamespace(api_key="x", base_url="", max_retries=0, retry_base_seconds=0.0),
    )
    p = provider_module.OpenAICompatibleProvider()
    try:
        p._require_enabled()
    except RuntimeError as exc:
        assert "KIVI_LLM_BASE_URL" in str(exc)
    else:
        raise AssertionError("invalid base URL should fail before an HTTP request")
