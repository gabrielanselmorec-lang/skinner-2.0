import pytest
import requests

from app.web import api_client


class FakeResponse:
    def __init__(self, payload=None, *, status_code=200, json_error=None):
        self.payload = payload
        self.status_code = status_code
        self.json_error = json_error

    def raise_for_status(self):
        if self.status_code >= 400:
            error = requests.HTTPError(f"HTTP {self.status_code}")
            error.response = self
            raise error

    def json(self):
        if self.json_error:
            raise self.json_error
        return self.payload


def test_get_json_raises_safe_error_for_http_failure(monkeypatch):
    monkeypatch.setattr(api_client.requests, "get", lambda *args, **kwargs: FakeResponse(status_code=503))
    with pytest.raises(api_client.APIClientError, match="HTTP 503"):
        api_client._get_json("/api/teste")


def test_get_json_raises_safe_error_for_invalid_json(monkeypatch):
    monkeypatch.setattr(
        api_client.requests,
        "get",
        lambda *args, **kwargs: FakeResponse(json_error=ValueError("conteúdo inválido")),
    )
    with pytest.raises(api_client.APIClientError, match="resposta inválida"):
        api_client._get_json("/api/teste")


def test_get_json_returns_valid_payload(monkeypatch):
    monkeypatch.setattr(api_client.requests, "get", lambda *args, **kwargs: FakeResponse({"ok": True}))
    assert api_client._get_json("/api/teste") == {"ok": True}
