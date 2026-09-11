"""OpenAI-compatible Chat Completions client with tool/function calling + mock fallback."""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

import httpx

from grok_org_os.config import get_settings

logger = logging.getLogger(__name__)

MOCK_MODELS = [
    {"id": "gpt-4o-mini", "owned_by": "openai"},
    {"id": "gpt-4o", "owned_by": "openai"},
    {"id": "gpt-4.1-mini", "owned_by": "openai"},
    {"id": "gpt-4.1", "owned_by": "openai"},
    {"id": "o3-mini", "owned_by": "openai"},
    {"id": "claude-3.5-sonnet", "owned_by": "anthropic"},
]


def normalize_base_url(url: str) -> str:
    """Strip trailing slash; append /v1 when user pastes a bare provider host."""
    u = (url or "").strip().rstrip("/")
    if not u:
        return "https://api.openai.com/v1"
    # Already has a version path
    lower = u.lower()
    if lower.endswith("/v1") or "/v1/" in lower or lower.endswith("/v1beta") or "/openai/deployments" in lower:
        return u
    # Common OpenAI-compatible hosts without /v1
    hosts = (
        "api.openai.com",
        "openrouter.ai/api",
        "api.groq.com/openai",
        "api.together.xyz",
        "api.fireworks.ai/inference",
        "integrate.api.nvidia.com",
        "api.deepseek.com",
        "api.mistral.ai",
    )
    for h in hosts:
        if lower.rstrip("/").endswith(h) or f"://{h}" in lower or lower.endswith(h):
            return f"{u}/v1"
    # Heuristic: bare https://host or https://host/api → try /v1
    from urllib.parse import urlparse

    parsed = urlparse(u if "://" in u else f"https://{u}")
    path = (parsed.path or "").rstrip("/")
    if path in ("", "/api"):
        return f"{u}/v1"
    return u




def parse_models_payload(payload: Any) -> list[dict[str, str]]:
    """Parse OpenAI-style {data:[{id}]} (or bare list) into [{id, owned_by}]."""
    raw = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(raw, list):
        raw = payload if isinstance(payload, list) else []
    models: list[dict[str, str]] = []
    for item in raw:
        if isinstance(item, dict) and item.get("id"):
            models.append(
                {
                    "id": str(item["id"]),
                    "owned_by": str(item.get("owned_by") or item.get("ownedBy") or ""),
                }
            )
        elif isinstance(item, str) and item.strip():
            models.append({"id": item.strip(), "owned_by": ""})
    return models


def _looks_chat_capable(model_id: str) -> bool:
    mid = (model_id or "").lower()
    # Deprioritize obvious non-chat endpoints when sorting
    skip = (
        "embed",
        "embedding",
        "rerank",
        "tts",
        "whisper",
        "transcri",
        "moderation",
        "dall-e",
        "stable-diffusion",
        "flux",
        "image",
        "video",
        "codec",
        "retrieve",
    )
    if any(s in mid for s in skip):
        return False
    return True


def sort_models_chat_first(models: list[dict[str, str]]) -> list[dict[str, str]]:
    """Full list sorted: chat-capable first, then alphabetical within groups."""
    return sorted(
        models,
        key=lambda m: (0 if _looks_chat_capable(m.get("id", "")) else 1, m.get("id", "").lower()),
    )


def _role_hint(system: str) -> str:
    s = system.lower()
    if "chief of staff" in s:
        return "chief_of_staff"
    if "ceo" in s and "chief" not in s:
        return "ceo"
    if "you are an ops" in s or "you are the ops" in s or s.startswith("ops "):
        return "ops"
    if "you are a research" in s or "you are the research" in s:
        return "research"
    if "you are a comms" in s or "you are the comms" in s:
        return "comms"
    if "ops specialist" in s or ("operations" in s and "specialist" in s):
        return "ops"
    if "research specialist" in s:
        return "research"
    if "comms specialist" in s or "communication specialist" in s:
        return "comms"
    return "generic"


class LLMClient:
    """POST {base_url}/chat/completions — mocks when no API key."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        settings = get_settings()
        self.api_key = api_key if api_key is not None else settings.openai_api_key
        self.base_url = normalize_base_url(base_url or settings.openai_base_url)
        self.model = model or settings.openai_model

    @property
    def use_mock(self) -> bool:
        return not bool(self.api_key and self.api_key.strip())

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float = 0.4,
        max_tokens: int = 1024,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict | None = None,
    ) -> str:
        """Return assistant text content (legacy). Ignores tool_calls."""
        msg = self.chat_message(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
            tool_choice=tool_choice,
        )
        return msg.get("content") or ""

    def chat_message(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float = 0.4,
        max_tokens: int = 1024,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict | None = None,
    ) -> dict[str, Any]:
        """Return full assistant message dict (content + optional tool_calls)."""
        if self.use_mock:
            return self._mock_message(messages, tools=tools)

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = tools
            if tool_choice is not None:
                payload["tool_choice"] = tool_choice
            else:
                payload["tool_choice"] = "auto"
        try:
            with httpx.Client(timeout=90.0) as client:
                resp = client.post(url, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM call failed (%s); falling back to mock", exc)
            return self._mock_message(messages, tools=tools)

    def chat_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        execute_tool: Callable[[str, dict[str, Any]], str],
        *,
        temperature: float = 0.4,
        max_tokens: int = 1024,
        max_rounds: int = 8,
        on_tool: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> str:
        """Run OpenAI tool-calling loop until final content or max_rounds."""
        msgs: list[dict[str, Any]] = list(messages)
        final = ""
        for _ in range(max_rounds):
            assistant = self.chat_message(
                msgs, temperature=temperature, max_tokens=max_tokens, tools=tools
            )
            tool_calls = assistant.get("tool_calls") or []
            content = assistant.get("content")
            # Append assistant turn (OpenAI wants content null when tool_calls present)
            assistant_msg: dict[str, Any] = {"role": "assistant", "content": content}
            if tool_calls:
                assistant_msg["tool_calls"] = tool_calls
                if content is None:
                    assistant_msg["content"] = None
            msgs.append(assistant_msg)
            if not tool_calls:
                final = content or ""
                break
            for tc in tool_calls:
                fn = tc.get("function") or {}
                name = fn.get("name") or ""
                raw_args = fn.get("arguments") or "{}"
                try:
                    args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
                except json.JSONDecodeError:
                    args = {"_raw": raw_args}
                if on_tool:
                    on_tool(name, args)
                result = execute_tool(name, args)
                msgs.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.get("id") or name,
                        "content": result if isinstance(result, str) else json.dumps(result),
                    }
                )
            else:
                continue
        else:
            # exhausted rounds — take last content if any
            final = final or (msgs[-1].get("content") if msgs else "") or ""
        return final or ""

    def list_models(self) -> dict[str, Any]:
        """GET {base_url}/models — curated mock list when no API key."""
        if self.use_mock:
            return {
                "ok": True,
                "mode": "mock",
                "base_url": self.base_url,
                "note": "No API key set — showing curated mock models. Add a key to fetch from the provider.",
                "models": list(MOCK_MODELS),
                "data": list(MOCK_MODELS),
            }
        url = f"{self.base_url.rstrip('/')}/models"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": "NEHA/2.1.4",
            "Accept": "application/json",
        }
        try:
            with httpx.Client(timeout=45.0, follow_redirects=True) as client:
                resp = client.get(url, headers=headers)
                if resp.status_code == 401:
                    return {
                        "ok": False,
                        "mode": "live",
                        "base_url": self.base_url,
                        "error": "401 Unauthorized — check API key",
                        "status_code": 401,
                        "models": [],
                        "data": [],
                    }
                if resp.status_code == 404:
                    return {
                        "ok": False,
                        "mode": "live",
                        "base_url": self.base_url,
                        "error": (
                            f"404 Not Found at {url}. "
                            "Check base URL (try with or without trailing /v1; trailing slash is stripped)."
                        ),
                        "status_code": 404,
                        "models": [],
                        "data": [],
                    }
                if resp.status_code >= 400:
                    detail = (resp.text or "")[:300]
                    return {
                        "ok": False,
                        "mode": "live",
                        "base_url": self.base_url,
                        "error": f"HTTP {resp.status_code}: {detail}",
                        "status_code": resp.status_code,
                        "models": [],
                        "data": [],
                    }
                payload = resp.json()
                models = parse_models_payload(payload)
                models = sort_models_chat_first(models)
                return {
                    "ok": True,
                    "mode": "live",
                    "base_url": self.base_url,
                    "models": models,
                    "data": models,
                    "count": len(models),
                }
        except httpx.TimeoutException as exc:
            return {
                "ok": False,
                "mode": "live",
                "base_url": self.base_url,
                "error": f"Timeout after 45s fetching models from {url}: {exc}",
                "models": [],
                "data": [],
            }
        except httpx.ConnectError as exc:
            return {
                "ok": False,
                "mode": "live",
                "base_url": self.base_url,
                "error": f"Connection failed to {url}: {exc}. Check base URL / network / SSL.",
                "models": [],
                "data": [],
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False,
                "mode": "live",
                "base_url": self.base_url,
                "error": str(exc),
                "models": [],
                "data": [],
            }

    def test_connection(self) -> dict[str, Any]:
        """Ping the model with a tiny completion; surface clear HTTP errors."""
        if self.use_mock:
            return {"ok": True, "mode": "mock", "model": self.model, "message": "Mock LLM ready"}
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "NEHA/2.1.4",
            "Accept": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": "Reply with exactly: pong"}],
            "max_tokens": 16,
            "temperature": 0,
        }
        try:
            with httpx.Client(timeout=45.0, follow_redirects=True) as client:
                resp = client.post(url, headers=headers, json=payload)
                if resp.status_code == 401:
                    return {
                        "ok": False,
                        "mode": "live",
                        "model": self.model,
                        "base_url": self.base_url,
                        "error": "401 Unauthorized — API key rejected. Check key and provider.",
                        "status_code": 401,
                    }
                if resp.status_code == 404:
                    return {
                        "ok": False,
                        "mode": "live",
                        "model": self.model,
                        "base_url": self.base_url,
                        "error": (
                            f"404 Not Found at {url}. "
                            "Normalize base URL (no trailing slash; often needs /v1). "
                            "Example: https://api.openai.com/v1 or https://openrouter.ai/api/v1"
                        ),
                        "status_code": 404,
                    }
                if resp.status_code >= 400:
                    return {
                        "ok": False,
                        "mode": "live",
                        "model": self.model,
                        "base_url": self.base_url,
                        "error": f"HTTP {resp.status_code}: {(resp.text or '')[:400]}",
                        "status_code": resp.status_code,
                    }
                data = resp.json()
                msg = data["choices"][0]["message"]
                return {
                    "ok": True,
                    "mode": "live",
                    "model": self.model,
                    "base_url": self.base_url,
                    "message": (msg.get("content") or "")[:200],
                }
        except httpx.TimeoutException as exc:
            return {
                "ok": False,
                "mode": "live",
                "model": self.model,
                "base_url": self.base_url,
                "error": f"Timeout after 45s testing {url}: {exc}",
            }
        except httpx.ConnectError as exc:
            return {
                "ok": False,
                "mode": "live",
                "model": self.model,
                "base_url": self.base_url,
                "error": f"Connection failed: {exc}. Wrong host, offline, or SSL error.",
            }
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "mode": "live", "model": self.model, "base_url": self.base_url, "error": str(exc)}

    def _mock_message(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Deterministic mock; emits tool_calls when tools provided and prompt asks."""
        user_bits = [
            m.get("content") or ""
            for m in messages
            if m.get("role") == "user" and isinstance(m.get("content"), str)
        ]
        system_bits = [
            m.get("content") or ""
            for m in messages
            if m.get("role") == "system" and isinstance(m.get("content"), str)
        ]
        last_user = user_bits[-1] if user_bits else ""
        system = " ".join(system_bits)
        lower = last_user.lower()
        role = _role_hint(system)
        tool_names = {t.get("function", {}).get("name") for t in (tools or []) if t.get("function")}

        # If prior tool results exist, synthesize final answer
        has_tool_results = any(m.get("role") == "tool" for m in messages)
        if has_tool_results and tools:
            return {
                "role": "assistant",
                "content": self._mock_text(role, last_user, lower, after_tools=True),
            }

        # Emit tool calls for CoS / specialists when tools available
        if tools and role == "chief_of_staff" and not has_tool_results:
            calls = []
            cid = 0
            if "list_agents" in tool_names:
                cid += 1
                calls.append(_tool_call(f"call_{cid}", "list_agents", {}))
            if "send_message" in tool_names:
                cid += 1
                calls.append(
                    _tool_call(
                        f"call_{cid}",
                        "send_message",
                        {
                            "content": f"CoS coordinating: {last_user[:160]}",
                        },
                    )
                )
            if "create_task" in tool_names:
                for focus in ("Ops", "Research", "Comms"):
                    cid += 1
                    calls.append(
                        _tool_call(
                            f"call_{cid}",
                            "create_task",
                            {
                                "title": f"{focus}: {last_user[:80] or 'work item'}",
                                "description": f"Subtask for {focus}. Parent context: {last_user[:200]}",
                                "assignee_hint": focus.lower(),
                            },
                        )
                    )
            if calls:
                return {"role": "assistant", "content": None, "tool_calls": calls}

        if tools and role in ("ops", "research", "comms") and not has_tool_results:
            calls = []
            cid = 0
            if "http_fetch" in tool_names and ("research" in role or "http" in lower or "web" in lower):
                cid += 1
                calls.append(
                    _tool_call(
                        f"call_{cid}",
                        "http_fetch",
                        {"url": "https://example.com", "max_chars": 500},
                    )
                )
            if "fs_list" in tool_names and ("file" in lower or "workspace" in lower or role == "ops"):
                cid += 1
                calls.append(_tool_call(f"call_{cid}", "fs_list", {"path": "."}))
            if "send_message" in tool_names:
                cid += 1
                calls.append(
                    _tool_call(
                        f"call_{cid}",
                        "send_message",
                        {"content": f"[{role}] Working on: {last_user[:120]}"},
                    )
                )
            if "request_approval" in tool_names and "approv" in lower:
                cid += 1
                calls.append(
                    _tool_call(
                        f"call_{cid}",
                        "request_approval",
                        {
                            "title": "CEO approval needed",
                            "description": last_user[:300],
                        },
                    )
                )
            if calls:
                return {"role": "assistant", "content": None, "tool_calls": calls}

        return {"role": "assistant", "content": self._mock_text(role, last_user, lower)}

    def _mock_text(
        self, role: str, last_user: str, lower: str, *, after_tools: bool = False
    ) -> str:
        if after_tools:
            if role == "chief_of_staff":
                return (
                    "[Chief of Staff] Coordination complete via tools. "
                    "Subtasks created and channel updated. Recommendation: proceed with "
                    "the phased pilot, validate via Research, and publish the Comms brief."
                )
            if role == "ops":
                return (
                    "[Ops Specialist] Operational assessment complete (tools used). "
                    "Resources are available; recommend phased rollout."
                )
            if role == "research":
                return (
                    "[Research Specialist] Research summary prepared with web/file tools. "
                    "Recommend validating assumptions with a short pilot."
                )
            if role == "comms":
                return (
                    "[Comms Specialist] Draft update ready. Stakeholders can be briefed."
                )
            return f"[Mock LLM] Completed after tool use regarding: {last_user[:200]}"

        if role == "ops":
            return (
                "[Ops Specialist] Operational assessment complete. "
                "Resources are available; recommend proceeding with a phased rollout. "
                f"Context considered: {last_user[:180]}"
            )
        if role == "research":
            return (
                "[Research Specialist] Research summary: key findings support the objective. "
                "Recommend validating assumptions with a short pilot. "
                f"Query: {last_user[:180]}"
            )
        if role == "comms":
            return (
                "[Comms Specialist] Draft update for stakeholders:\n"
                "We have coordinated Ops and Research inputs and are ready to share a concise plan. "
                f"Subject: {last_user[:120]}"
            )
        if role == "chief_of_staff":
            if "synthesize" in lower:
                return (
                    "[Chief of Staff] Coordination complete. Subtasks executed; synthesizing "
                    "results into an executive brief for the CEO. Recommendation: proceed with "
                    "the phased pilot, validate via Research, and publish the Comms brief."
                )
            if "decompose" in lower or "break down" in lower or "subtask" in lower:
                return (
                    "DECOMPOSE:\n"
                    "1. [Ops] Assess operational readiness and constraints\n"
                    "2. [Research] Gather relevant background and options\n"
                    "3. [Comms] Draft a clear stakeholder summary\n"
                    "ASSIGN each subtask to the matching specialist team."
                )
            return (
                "[Chief of Staff] Acknowledged. Coordinating Ops, Research, and Comms now."
            )
        if role == "ceo":
            return "[CEO] Direction acknowledged. Proceed with the plan."
        if "decompose" in lower or "break down" in lower:
            return (
                "DECOMPOSE:\n"
                "1. [Ops] Assess operational readiness and constraints\n"
                "2. [Research] Gather relevant background and options\n"
                "3. [Comms] Draft a clear stakeholder summary\n"
                "ASSIGN each subtask to the matching specialist team."
            )
        if "synthesize" in lower:
            return (
                "[Chief of Staff] Coordination complete. Subtasks executed; synthesizing "
                "results into an executive brief for the CEO."
            )
        return (
            f"[Mock LLM] Processed request with {len(last_user)} chars of user input. "
            f"Response regarding: {last_user[:240] or 'general task'}"
        )


def _tool_call(call_id: str, name: str, args: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(args)},
    }


_default_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    global _default_client
    if _default_client is None:
        _default_client = LLMClient()
    return _default_client


def set_llm_client(client: LLMClient | None) -> None:
    global _default_client
    _default_client = client
