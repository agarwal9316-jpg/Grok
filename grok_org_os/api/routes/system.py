"""System routes: settings/config, bootstrap, demo, test LLM, agent status."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from grok_org_os.api.deps import get_db
from grok_org_os.bootstrap import bootstrap_sample_org
from grok_org_os.config import get_settings, reset_settings_cache
from grok_org_os.llm import LLMClient, normalize_base_url, set_llm_client
from grok_org_os.providers import list_providers
from grok_org_os.models import Message, Task, TaskStatus
from grok_org_os.schemas import (
    AgentRead,
    ChannelRead,
    OrganisationRead,
    TaskRead,
)

router = APIRouter(tags=["system"])

ENV_PATH = Path(".env")


class ConfigRead(BaseModel):
    openai_base_url: str
    openai_model: str
    api_key_set: bool
    has_llm_key: bool
    use_mock: bool
    database_url: str
    host: str
    port: int
    version: str = "2.1.2"
    workspace_dir: str = "workspace"


class SettingsUpdate(BaseModel):
    openai_api_key: Optional[str] = None
    openai_base_url: Optional[str] = Field(None, min_length=1)
    openai_model: Optional[str] = Field(None, min_length=1)
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_from: Optional[str] = None
    webhook_url: Optional[str] = None


class LlmOverrideBody(BaseModel):
    """Optional form-value overrides so fetch/test work before Save."""

    openai_api_key: Optional[str] = None
    openai_base_url: Optional[str] = None
    openai_model: Optional[str] = None


class BootstrapRequest(BaseModel):
    name: str = "Grok Demo Org"


class BootstrapResponse(BaseModel):
    organisation: OrganisationRead
    agents: dict[str, AgentRead]
    channel: ChannelRead
    teams: dict[str, dict]


class DemoRequest(BaseModel):
    org_name: str = "Grok Demo Org"
    title: str = "Launch Q4 product pilot"
    description: str = (
        "Coordinate Ops, Research, and Comms to prepare a Q4 product pilot plan."
    )


class DemoResponse(BaseModel):
    task: TaskRead
    message_count: int
    channel: ChannelRead
    used_tools: bool = True
    mode: str = "mock"


def _read_env_file() -> dict[str, str]:
    data: dict[str, str] = {}
    if not ENV_PATH.exists():
        return data
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        data[key.strip()] = value.strip()
    return data


def _write_env_file(updates: dict[str, str]) -> None:
    existing = _read_env_file()
    existing.update({k: v for k, v in updates.items() if v is not None})
    lines = [
        "# OpenAI-compatible LLM settings (optional — mock used if OPENAI_API_KEY unset)",
        f"OPENAI_API_KEY={existing.get('OPENAI_API_KEY', '')}",
        f"OPENAI_BASE_URL={existing.get('OPENAI_BASE_URL', 'https://api.openai.com/v1')}",
        f"OPENAI_MODEL={existing.get('OPENAI_MODEL', 'gpt-4o-mini')}",
        "",
        "# App",
        f"DATABASE_URL={existing.get('DATABASE_URL', 'sqlite:///./grok_org_os.db')}",
        f"HOST={existing.get('HOST', '0.0.0.0')}",
        f"PORT={existing.get('PORT', '8000')}",
        f"WORKSPACE_DIR={existing.get('WORKSPACE_DIR', 'workspace')}",
        "",
        "# Connectors (optional)",
        f"SMTP_HOST={existing.get('SMTP_HOST', '')}",
        f"SMTP_PORT={existing.get('SMTP_PORT', '587')}",
        f"SMTP_USER={existing.get('SMTP_USER', '')}",
        f"SMTP_PASSWORD={existing.get('SMTP_PASSWORD', '')}",
        f"SMTP_FROM={existing.get('SMTP_FROM', '')}",
        f"WEBHOOK_URL={existing.get('WEBHOOK_URL', '')}",
        f"REST_BASE_URL={existing.get('REST_BASE_URL', '')}",
        f"REST_API_TOKEN={existing.get('REST_API_TOKEN', '')}",
        f"GOOGLE_CLIENT_ID={existing.get('GOOGLE_CLIENT_ID', '')}",
        f"GOOGLE_CLIENT_SECRET={existing.get('GOOGLE_CLIENT_SECRET', '')}",
        f"GOOGLE_REFRESH_TOKEN={existing.get('GOOGLE_REFRESH_TOKEN', '')}",
        "",
    ]
    ENV_PATH.write_text("\n".join(lines), encoding="utf-8")


def _config_read() -> ConfigRead:
    from grok_org_os import __version__

    s = get_settings()
    return ConfigRead(
        openai_base_url=s.openai_base_url,
        openai_model=s.openai_model,
        api_key_set=s.has_llm_key,
        has_llm_key=s.has_llm_key,
        use_mock=not s.has_llm_key,
        database_url=s.database_url,
        host=s.host,
        port=s.port,
        version=__version__,
        workspace_dir=s.workspace_dir,
    )


@router.get("/config", response_model=ConfigRead)
@router.get("/settings", response_model=ConfigRead)
def get_app_settings() -> ConfigRead:
    return _config_read()


@router.put("/settings", response_model=ConfigRead)
@router.put("/config", response_model=ConfigRead)
def update_app_settings(payload: SettingsUpdate) -> ConfigRead:
    updates: dict[str, str] = {}
    if payload.openai_api_key is not None:
        updates["OPENAI_API_KEY"] = payload.openai_api_key
    if payload.openai_base_url is not None:
        updates["OPENAI_BASE_URL"] = normalize_base_url(payload.openai_base_url)
    if payload.openai_model is not None:
        updates["OPENAI_MODEL"] = payload.openai_model
    if payload.smtp_host is not None:
        updates["SMTP_HOST"] = payload.smtp_host
    if payload.smtp_port is not None:
        updates["SMTP_PORT"] = str(payload.smtp_port)
    if payload.smtp_user is not None:
        updates["SMTP_USER"] = payload.smtp_user
    if payload.smtp_password is not None:
        updates["SMTP_PASSWORD"] = payload.smtp_password
    if payload.smtp_from is not None:
        updates["SMTP_FROM"] = payload.smtp_from
    if payload.webhook_url is not None:
        updates["WEBHOOK_URL"] = payload.webhook_url
    if not updates:
        raise HTTPException(status_code=400, detail="No settings to update")
    _write_env_file(updates)
    reset_settings_cache()
    import os

    for k, v in updates.items():
        os.environ[k] = v
    set_llm_client(None)
    return _config_read()



def _client_from_overrides(payload: LlmOverrideBody | None = None) -> LLMClient:
    """Build LLMClient using optional JSON body overrides (form values)."""
    settings = get_settings()
    key = settings.openai_api_key
    base = settings.openai_base_url
    model = settings.openai_model
    if payload is not None:
        if payload.openai_api_key is not None and str(payload.openai_api_key).strip():
            key = str(payload.openai_api_key).strip()
        if payload.openai_base_url is not None and str(payload.openai_base_url).strip():
            base = normalize_base_url(str(payload.openai_base_url).strip())
        if payload.openai_model is not None and str(payload.openai_model).strip():
            model = str(payload.openai_model).strip()
    return LLMClient(api_key=key or "", base_url=base, model=model)


async def _parse_override_body(request: Request) -> LlmOverrideBody | None:
    """Accept JSON body overrides on GET or POST (empty/missing body → None)."""
    ctype = (request.headers.get("content-type") or "").lower()
    if "application/json" not in ctype and request.method == "GET":
        # Allow query params as a convenience for GET
        qp = request.query_params
        if not any(k in qp for k in ("openai_api_key", "openai_base_url", "openai_model")):
            return None
        return LlmOverrideBody(
            openai_api_key=qp.get("openai_api_key"),
            openai_base_url=qp.get("openai_base_url"),
            openai_model=qp.get("openai_model"),
        )
    try:
        raw = await request.body()
        if not raw or not raw.strip():
            return None
        import json

        data = json.loads(raw)
        if not isinstance(data, dict):
            return None
        return LlmOverrideBody(
            openai_api_key=data.get("openai_api_key"),
            openai_base_url=data.get("openai_base_url"),
            openai_model=data.get("openai_model"),
        )
    except Exception:  # noqa: BLE001
        return None


@router.get("/providers")
def get_providers() -> dict:
    """Built-in provider catalog (base URLs) shared by PC + Android."""
    return list_providers()


@router.get("/models")
async def list_provider_models_get(request: Request) -> dict:
    """List models (GET). Accepts optional JSON/query overrides."""
    payload = await _parse_override_body(request)
    return _client_from_overrides(payload).list_models()


@router.post("/models")
async def list_provider_models_post(request: Request) -> dict:
    """List models (POST). JSON body overrides: openai_api_key, openai_base_url."""
    payload = await _parse_override_body(request)
    return _client_from_overrides(payload).list_models()


@router.post("/settings/test")
@router.post("/config/test")
async def test_llm_connection(request: Request) -> dict:
    """Ping chat/completions. Accepts JSON body overrides for key/base/model."""
    payload = await _parse_override_body(request)
    client = _client_from_overrides(payload)
    return client.test_connection()


@router.post("/bootstrap", response_model=BootstrapResponse)
def bootstrap_org(
    payload: BootstrapRequest = BootstrapRequest(),
    db: Session = Depends(get_db),
) -> BootstrapResponse:
    name = payload.name or "Grok Demo Org"
    data = bootstrap_sample_org(db, name=name)
    return BootstrapResponse(
        organisation=OrganisationRead.model_validate(data["organisation"]),
        agents={k: AgentRead.model_validate(v) for k, v in data["agents"].items()},
        channel=ChannelRead.model_validate(data["channel"]),
        teams={
            k: {"id": v.id, "name": v.name, "description": v.description}
            for k, v in data["teams"].items()
        },
    )


@router.post("/demo", response_model=DemoResponse)
def run_demo(
    payload: DemoRequest = DemoRequest(),
    db: Session = Depends(get_db),
) -> DemoResponse:
    """Create a task, assign to Chief of Staff, run tool-calling collaboration."""
    set_llm_client(LLMClient())
    llm = LLMClient()
    data = bootstrap_sample_org(db, name=payload.org_name or "Grok Demo Org")
    org = data["organisation"]
    cos = data["agents"]["chief_of_staff"]
    channel = data["channel"]
    ceo = data["agents"]["ceo"]

    from grok_org_os.task_runner import TaskRunner

    runner = TaskRunner(db, llm=llm)
    runner.post_message(
        channel,
        ceo,
        f"Directive: {payload.title}\n{payload.description}\nPlease coordinate the teams.",
    )

    task = Task(
        organisation_id=org.id,
        title=payload.title,
        description=payload.description,
        status=TaskStatus.pending,
        channel_id=channel.id,
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    result = runner.assign_task(task, cos, channel, run=True)
    msg_count = db.query(Message).filter(Message.channel_id == channel.id).count()
    return DemoResponse(
        task=TaskRead.model_validate(result),
        message_count=msg_count,
        channel=ChannelRead.model_validate(channel),
        used_tools=True,
        mode="live" if not llm.use_mock else "mock",
    )
