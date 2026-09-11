"""Providers catalog + /api/models and /api/settings/test body overrides."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from grok_org_os.llm import LLMClient, parse_models_payload, sort_models_chat_first
from grok_org_os.providers import list_providers, match_provider_id


NVIDIA_FIXTURE = {
    "object": "list",
    "data": [
        {"id": "meta/llama-3.1-8b-instruct", "owned_by": "meta"},
        {"id": "nvidia/nv-embedqa-e5-v5", "owned_by": "nvidia"},
        {"id": "01-ai/yi-large", "owned_by": "01-ai"},
        {"id": "openai/whisper-large-v3", "owned_by": "openai"},
    ],
}


def test_providers_catalog_api(client):
    res = client.get("/api/providers")
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["count"] >= 10
    ids = {p["id"] for p in body["providers"]}
    assert "openai" in ids
    assert "nvidia" in ids
    assert "ollama" in ids
    assert "custom" in ids
    nvidia = next(p for p in body["providers"] if p["id"] == "nvidia")
    assert nvidia["base_url"] == "https://integrate.api.nvidia.com/v1"


def test_list_providers_module():
    data = list_providers()
    assert data["count"] == len(data["providers"])
    assert match_provider_id("https://integrate.api.nvidia.com/v1") == "nvidia"
    assert match_provider_id("https://api.openai.com/v1") == "openai"
    assert match_provider_id("https://example.com/v1") == "custom"


def test_parse_models_payload_fixture():
    models = parse_models_payload(NVIDIA_FIXTURE)
    assert len(models) == 4
    ids = [m["id"] for m in models]
    assert "meta/llama-3.1-8b-instruct" in ids
    sorted_m = sort_models_chat_first(models)
    # chat-capable before embed/whisper
    assert sorted_m[0]["id"] in ("01-ai/yi-large", "meta/llama-3.1-8b-instruct")
    assert sorted_m[-1]["id"] in ("nvidia/nv-embedqa-e5-v5", "openai/whisper-large-v3")


def test_models_post_body_overrides_without_saving(client):
    """POST /api/models uses JSON body key/base even when .env has no key."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = NVIDIA_FIXTURE
    mock_resp.text = ""

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get.return_value = mock_resp

    with patch("grok_org_os.llm.httpx.Client", return_value=mock_client):
        res = client.post(
            "/api/models",
            json={
                "openai_api_key": "test-key-not-saved",
                "openai_base_url": "https://integrate.api.nvidia.com/v1",
            },
        )
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["mode"] == "live"
    assert body["count"] == 4
    assert len(body["models"]) == 4
    call_url = mock_client.get.call_args[0][0]
    assert "integrate.api.nvidia.com" in call_url
    assert call_url.endswith("/models")
    # Settings should still be mock (no key saved)
    cfg = client.get("/api/config").json()
    assert cfg["has_llm_key"] is False


def test_settings_test_body_overrides(client):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": "pong"}}]
    }
    mock_resp.text = ""

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.post.return_value = mock_resp

    with patch("grok_org_os.llm.httpx.Client", return_value=mock_client):
        res = client.post(
            "/api/settings/test",
            json={
                "openai_api_key": "sk-test",
                "openai_base_url": "https://integrate.api.nvidia.com/v1",
                "openai_model": "meta/llama-3.1-8b-instruct",
            },
        )
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["mode"] == "live"
    assert "pong" in (body.get("message") or "")
    call_url = mock_client.post.call_args[0][0]
    assert call_url.endswith("/chat/completions")


def test_settings_test_timeout_error(client):
    import httpx

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.post.side_effect = httpx.TimeoutException("timed out")

    with patch("grok_org_os.llm.httpx.Client", return_value=mock_client):
        res = client.post(
            "/api/settings/test",
            json={
                "openai_api_key": "sk-test",
                "openai_base_url": "https://integrate.api.nvidia.com/v1",
                "openai_model": "x",
            },
        )
    body = res.json()
    assert body["ok"] is False
    assert "Timeout" in body["error"] or "timeout" in body["error"].lower()


def test_llm_client_list_models_nvidia_fixture_unit():
    client = LLMClient(
        api_key="test",
        base_url="https://integrate.api.nvidia.com/v1",
        model="x",
    )
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = NVIDIA_FIXTURE
    mock_resp.text = ""
    mock_http = MagicMock()
    mock_http.__enter__ = MagicMock(return_value=mock_http)
    mock_http.__exit__ = MagicMock(return_value=False)
    mock_http.get.return_value = mock_resp
    with patch("grok_org_os.llm.httpx.Client", return_value=mock_http):
        out = client.list_models()
    assert out["ok"] is True
    assert out["count"] == 4
