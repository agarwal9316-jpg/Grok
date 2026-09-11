"""OpenAI-compatible Chat Completions client with mock fallback."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from grok_org_os.config import get_settings

logger = logging.getLogger(__name__)


def _role_hint(system: str) -> str:
    """Classify agent role from system prompt (order matters)."""
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
    # Fallback heuristics for shorter prompts
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
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.4,
        max_tokens: int = 1024,
    ) -> str:
        if self.use_mock:
            return self._mock_response(messages)

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
        try:
            with httpx.Client(timeout=60.0) as client:
                resp = client.post(url, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"]
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM call failed (%s); falling back to mock", exc)
            return self._mock_response(messages)

    def _mock_response(self, messages: list[dict[str, str]]) -> str:
        """Deterministic mock that still enables end-to-end collaboration demos."""
        user_bits = [m["content"] for m in messages if m.get("role") == "user"]
        system_bits = [m["content"] for m in messages if m.get("role") == "system"]
        last_user = user_bits[-1] if user_bits else ""
        system = " ".join(system_bits)
        lower = last_user.lower()
        role = _role_hint(system)

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
            f"[Mock LLM] Processed request with {len(messages)} message(s). "
            f"Response regarding: {last_user[:240] or 'general task'}"
        )


_default_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    global _default_client
    if _default_client is None:
        _default_client = LLMClient()
    return _default_client


def set_llm_client(client: LLMClient | None) -> None:
    global _default_client
    _default_client = client
