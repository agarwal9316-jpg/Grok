"""Built-in OpenAI-compatible provider catalog (shared PC + Android via GET /api/providers)."""

from __future__ import annotations

from typing import Any

PROVIDERS: list[dict[str, Any]] = [
    {
        "id": "openai",
        "name": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "editable": True,
    },
    {
        "id": "openrouter",
        "name": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "editable": True,
    },
    {
        "id": "groq",
        "name": "Groq",
        "base_url": "https://api.groq.com/openai/v1",
        "editable": True,
    },
    {
        "id": "nvidia",
        "name": "NVIDIA NIM",
        "base_url": "https://integrate.api.nvidia.com/v1",
        "editable": True,
    },
    {
        "id": "together",
        "name": "Together",
        "base_url": "https://api.together.xyz/v1",
        "editable": True,
    },
    {
        "id": "fireworks",
        "name": "Fireworks",
        "base_url": "https://api.fireworks.ai/inference/v1",
        "editable": True,
    },
    {
        "id": "deepseek",
        "name": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "editable": True,
    },
    {
        "id": "mistral",
        "name": "Mistral",
        "base_url": "https://api.mistral.ai/v1",
        "editable": True,
    },
    {
        "id": "google",
        "name": "Google AI Studio (OpenAI compat)",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "editable": True,
    },
    {
        "id": "azure",
        "name": "Azure OpenAI",
        "base_url": "https://YOUR_RESOURCE.openai.azure.com/openai/v1",
        "editable": True,
        "placeholder": True,
    },
    {
        "id": "ollama",
        "name": "Ollama",
        "base_url": "http://127.0.0.1:11434/v1",
        "editable": True,
    },
    {
        "id": "lmstudio",
        "name": "LM Studio",
        "base_url": "http://127.0.0.1:1234/v1",
        "editable": True,
    },
    {
        "id": "custom",
        "name": "Custom",
        "base_url": "",
        "editable": True,
    },
]


def list_providers() -> dict[str, Any]:
    return {
        "ok": True,
        "providers": list(PROVIDERS),
        "count": len(PROVIDERS),
    }


def match_provider_id(base_url: str) -> str:
    """Best-effort match of a base URL to a catalog id."""
    u = (base_url or "").strip().rstrip("/").lower()
    if not u:
        return "custom"
    for p in PROVIDERS:
        if p["id"] == "custom":
            continue
        bu = (p.get("base_url") or "").rstrip("/").lower()
        if not bu or "your_resource" in bu:
            continue
        if u == bu or u.startswith(bu) or bu.startswith(u):
            return p["id"]
    return "custom"
