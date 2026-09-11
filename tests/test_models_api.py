"""Tests for GET/POST /api/models and base URL normalization."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from grok_org_os.llm import LLMClient, normalize_base_url


def _clear_key(client):
    client.put("/api/settings", json={"openai_api_key": ""})




@pytest.mark.parametrize(
    "raw,expected",
    [
        ("https://api.openai.com/v1/", "https://api.openai.com/v1"),
        ("https://api.openai.com", "https://api.openai.com/v1"),
        ("https://openrouter.ai/api", "https://openrouter.ai/api/v1"),
        ("https://openrouter.ai/api/v1", "https://openrouter.ai/api/v1"),
        ("https://api.groq.com/openai", "https://api.groq.com/openai/v1"),
        ("", "https://api.openai.com/v1"),
    ],
)
def test_normalize_base_url(raw, expected):
    assert normalize_base_url(raw) == expected


def test_list_models_mock_when_no_key(client):
    res = client.get("/api/models")
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["mode"] == "mock"
    assert data["note"]
    ids = [m["id"] for m in data["models"]]
    assert "gpt-4o-mini" in ids
    assert "gpt-4o" in ids


def test_list_models_post_mock(client):
    res = client.post("/api/models")
    assert res.status_code == 200
    assert res.json()["mode"] == "mock"


def test_list_models_live_httpx(monkeypatch, tmp_path, client):
    """When key is set, /api/models calls {base}/models via httpx."""
    # Persist settings so LLMClient picks up key
    r = client.put(
        "/api/settings",
        json={
            "openai_api_key": "sk-test-key",
            "openai_base_url": "https://api.openai.com/v1",
            "openai_model": "gpt-4o-mini",
        },
    )
    assert r.status_code == 200
    assert r.json()["has_llm_key"] is True

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "data": [
            {"id": "gpt-4o", "owned_by": "openai"},
            {"id": "gpt-4o-mini", "owned_by": "openai"},
        ]
    }
    mock_resp.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get.return_value = mock_resp

    with patch("grok_org_os.llm.httpx.Client", return_value=mock_client):
        res = client.get("/api/models")
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["mode"] == "live"
    ids = [m["id"] for m in body["models"]]
    assert ids == ["gpt-4o", "gpt-4o-mini"]  # sorted
    mock_client.get.assert_called()
    call_url = mock_client.get.call_args[0][0]
    assert call_url.endswith("/models")
    _clear_key(client)


def test_list_models_401(client):
    client.put(
        "/api/settings",
        json={"openai_api_key": "sk-bad", "openai_base_url": "https://api.openai.com/v1"},
    )
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.text = "Unauthorized"

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get.return_value = mock_resp

    with patch("grok_org_os.llm.httpx.Client", return_value=mock_client):
        res = client.get("/api/models")
    body = res.json()
    assert body["ok"] is False
    assert "401" in body["error"]
    _clear_key(client)


def test_list_models_404_wrong_url(client):
    client.put(
        "/api/settings",
        json={"openai_api_key": "sk-test", "openai_base_url": "https://example.com"},
    )
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_resp.text = "not found"

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get.return_value = mock_resp

    with patch("grok_org_os.llm.httpx.Client", return_value=mock_client):
        res = client.post("/api/models")
    body = res.json()
    assert body["ok"] is False
    assert "404" in body["error"]
    _clear_key(client)


def test_test_connection_clear_401(client):
    client.put(
        "/api/settings",
        json={
            "openai_api_key": "sk-bad",
            "openai_base_url": "https://api.openai.com/v1",
            "openai_model": "gpt-4o-mini",
        },
    )
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.text = "Unauthorized"

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.post.return_value = mock_resp

    with patch("grok_org_os.llm.httpx.Client", return_value=mock_client):
        res = client.post("/api/settings/test")
    body = res.json()
    assert body["ok"] is False
    assert "401" in body["error"]
    _clear_key(client)


def test_settings_put_model_updates_config(client):
    res = client.put("/api/settings", json={"openai_model": "gpt-4o"})
    assert res.status_code == 200
    assert res.json()["openai_model"] == "gpt-4o"
    cfg = client.get("/api/config").json()
    assert cfg["openai_model"] == "gpt-4o"
