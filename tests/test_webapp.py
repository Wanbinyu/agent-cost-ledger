from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent_cost_ledger.webapp import create_app


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("COST_LEDGER_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    app = create_app(tmp_path)
    return TestClient(app)


def test_index_and_health(client: TestClient) -> None:
    r = client.get("/")
    assert r.status_code == 200
    assert "Usage Chat" in r.text
    assert "usage-bar" in r.text
    h = client.get("/api/health")
    assert h.status_code == 200
    assert h.json()["ok"] is True


def test_settings_roundtrip(client: TestClient) -> None:
    r = client.get("/api/settings")
    assert r.status_code == 200
    assert r.json()["ready"] is False

    r = client.post(
        "/api/settings",
        json={
            "provider": "openai",
            "base_url": "https://example.com/v1",
            "api_key": "sk-test-key-123456",
            "model": "demo-model",
            "input_price_per_1m": 1.0,
            "output_price_per_1m": 2.0,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ready"] is True
    assert body["has_api_key"] is True
    assert "api_key" not in body
    assert "sk-test-key-123456" not in str(body)
    assert body["model"] == "demo-model"


def test_chat_auto_ledger(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    client.post(
        "/api/settings",
        json={
            "base_url": "https://example.com/v1",
            "api_key": "sk-test",
            "model": "demo",
            "provider": "openai",
            "input_price_per_1m": 1.0,
            "output_price_per_1m": 2.0,
        },
    )

    async def fake_chat(settings, messages, timeout=120.0):  # noqa: ANN001
        return {
            "content": "hello back",
            "input_tokens": 10,
            "output_tokens": 5,
            "cache_read_tokens": 0,
            "cache_creation_tokens": 0,
            "raw_model": "demo",
            "finish_reason": "stop",
            "usage_missing": False,
            "cost_usd": None,
        }

    monkeypatch.setattr(
        "agent_cost_ledger.webapp.chat_completion",
        fake_chat,
    )

    r = client.post("/api/chat", json={"message": "hi there"})
    assert r.status_code == 200
    data = r.json()
    assert data["message"]["content"] == "hello back"
    assert data["session_usage"]["input_tokens"] == 10
    assert data["session_usage"]["output_tokens"] == 5
    assert data["session_usage"]["cost_usd"] is not None
    assert data["total_usage"]["events"] >= 1

    # usage API
    sid = data["session_id"]
    u = client.get(f"/api/usage?session_id={sid}")
    assert u.status_code == 200
    assert u.json()["input_tokens"] == 10


def test_chat_requires_config(client: TestClient) -> None:
    r = client.post("/api/chat", json={"message": "hi"})
    assert r.status_code == 502


def test_chat_usage_missing_not_zero_cost(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    client.post(
        "/api/settings",
        json={
            "base_url": "https://example.com/v1",
            "api_key": "sk-test",
            "model": "demo",
            "provider": "openai",
            "input_price_per_1m": 1.0,
            "output_price_per_1m": 2.0,
        },
    )

    async def fake_chat(settings, messages, timeout=120.0):  # noqa: ANN001
        return {
            "content": "no usage",
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_read_tokens": 0,
            "cache_creation_tokens": 0,
            "raw_model": "demo",
            "finish_reason": "stop",
            "usage_missing": True,
            "cost_usd": None,
        }

    monkeypatch.setattr("agent_cost_ledger.webapp.chat_completion", fake_chat)
    r = client.post("/api/chat", json={"message": "hi"})
    assert r.status_code == 200
    data = r.json()
    assert data["usage_event"]["usage_missing"] is True
    assert data["usage_event"]["cost_usd"] is None
    assert data["usage_event"]["cost_is_partial"] is True
    assert data["session_usage"]["cost_is_partial"] is True

