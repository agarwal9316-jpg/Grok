"""Tests for NVIDIA detection, key trim, and Test connection error helpers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from grok_org_os.llm import (
    NVIDIA_FALLBACK_MODEL,
    LLMClient,
    format_llm_http_error,
    is_nvidia_host,
    looks_openai_model,
    resolve_nvidia_test_model,
    trim_api_key,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("sk-abc", "sk-abc"),
        ("  sk-abc\n", "sk-abc"),
        ("sk-abc\r\n", "sk-abc"),
        ("\ufeffsk-abc", "sk-abc"),
        ("\n\n  \t", ""),
        (None, ""),
        ("", ""),
    ],
)
def test_trim_api_key(raw, expected):
    assert trim_api_key(raw) == expected


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://integrate.api.nvidia.com/v1", True),
        ("https://api.openai.com/v1", False),
        ("https://build.nvidia.com", True),
        ("", False),
    ],
)
def test_is_nvidia_host(url, expected):
    assert is_nvidia_host(url) is expected


@pytest.mark.parametrize(
    "model,expected",
    [
        ("gpt-4o-mini", True),
        ("gpt-4o", True),
        ("o1-mini", True),
        ("o3-mini", True),
        ("meta/llama-3.1-8b-instruct", False),
        ("nvidia/llama", False),
        ("", False),
    ],
)
def test_looks_openai_model(model, expected):
    assert looks_openai_model(model) is expected


def test_resolve_nvidia_test_model_fallback():
    assert (
        resolve_nvidia_test_model(
            "https://integrate.api.nvidia.com/v1", "gpt-4o-mini", None
        )
        == NVIDIA_FALLBACK_MODEL
    )


def test_resolve_nvidia_test_model_uses_fetched():
    ids = ["meta/llama-3.1-70b-instruct", "something-else"]
    assert (
        resolve_nvidia_test_model(
            "https://integrate.api.nvidia.com/v1", "gpt-4o-mini", ids
        )
        == "meta/llama-3.1-70b-instruct"
    )


def test_resolve_non_nvidia_unchanged():
    assert (
        resolve_nvidia_test_model("https://api.openai.com/v1", "gpt-4o-mini", None)
        == "gpt-4o-mini"
    )


def test_format_nvidia_401_entitlement():
    msg = format_llm_http_error(
        401,
        "https://integrate.api.nvidia.com/v1",
        "meta/llama-3.1-8b-instruct",
        '{"detail":"Unauthorized"}',
    )
    assert "Public API Endpoints" in msg
    assert "build.nvidia.com" in msg
    assert "401" in msg
    assert "Unauthorized" in msg


def test_format_nvidia_403_entitlement():
    msg = format_llm_http_error(
        403,
        "https://integrate.api.nvidia.com/v1",
        "meta/llama-3.1-8b-instruct",
        "forbidden",
    )
    assert "Public API Endpoints" in msg
    assert "403" in msg


def test_format_nvidia_400_wrong_model():
    msg = format_llm_http_error(
        400,
        "https://integrate.api.nvidia.com/v1",
        "gpt-4o-mini",
        '{"error":"model not found"}',
    )
    assert "pick a NVIDIA model" in msg
    assert "gpt-4o-mini" in msg


def test_test_connection_nvidia_401_message(client):
    client.put(
        "/api/settings",
        json={
            "openai_api_key": "nvapi-test",
            "openai_base_url": "https://integrate.api.nvidia.com/v1",
            "openai_model": "meta/llama-3.1-8b-instruct",
        },
    )
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.text = '{"status":401,"title":"Unauthorized"}'

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.post.return_value = mock_resp

    with patch("grok_org_os.llm.httpx.Client", return_value=mock_client):
        res = client.post("/api/settings/test")
    body = res.json()
    assert body["ok"] is False
    assert "Public API Endpoints" in body["error"]
    assert body.get("body")
    client.put("/api/settings", json={"openai_api_key": ""})


def test_test_connection_nvidia_swaps_gpt_model(client):
    client.put(
        "/api/settings",
        json={
            "openai_api_key": "nvapi-test",
            "openai_base_url": "https://integrate.api.nvidia.com/v1",
            "openai_model": "gpt-4o-mini",
        },
    )
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = ""
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": "pong"}}]
    }

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.post.return_value = mock_resp

    with patch("grok_org_os.llm.httpx.Client", return_value=mock_client):
        res = client.post("/api/settings/test")
    body = res.json()
    assert body["ok"] is True
    assert body["model"] == NVIDIA_FALLBACK_MODEL
    call_kwargs = mock_client.post.call_args
    payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
    assert payload["model"] == NVIDIA_FALLBACK_MODEL
    client.put("/api/settings", json={"openai_api_key": ""})


def test_settings_reject_whitespace_only_key(client):
    res = client.put("/api/settings", json={"openai_api_key": "  \n\t  "})
    assert res.status_code == 400
    assert "empty after trim" in res.json()["detail"].lower()


def test_client_trims_key_on_init():
    c = LLMClient(
        api_key="  sk-x\n",
        base_url="https://api.openai.com/v1",
        model="gpt-4o-mini",
    )
    assert c.api_key == "sk-x"
