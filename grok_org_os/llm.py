"""OpenAI-compatible Chat Completions client with tool/function calling + mock fallback."""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

import httpx

from grok_org_os.config import get_settings

logger = logging.getLogger(__name__)


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
        self.base_url = (base_url or settings.openai_base_url).rstrip("/")
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
            # Append assistant turn
            msgs.append(
                {
                    "role": "assistant",
                    "content": content,
                    **({"tool_calls": tool_calls} if tool_calls else {}),
                }
            )
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

    def test_connection(self) -> dict[str, Any]:
        """Ping the model with a tiny completion."""
        if self.use_mock:
            return {"ok": True, "mode": "mock", "model": self.model, "message": "Mock LLM ready"}
        try:
            msg = self.chat_message(
                [{"role": "user", "content": "Reply with exactly: pong"}],
                max_tokens=16,
                temperature=0,
            )
            return {
                "ok": True,
                "mode": "live",
                "model": self.model,
                "base_url": self.base_url,
                "message": (msg.get("content") or "")[:200],
            }
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "mode": "live", "error": str(exc)}

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
            if "create_task" in tool_names and (
                "decompose" in lower or "break down" in lower or "subtask" in lower or "coordinate" in lower
                or "task" in lower or True
            ):
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
