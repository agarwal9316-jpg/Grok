"""Pydantic v2 request/response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from grok_org_os.models import AgentRole, ApprovalStatus, TaskStatus


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- Organisation ---
class OrganisationCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None


class OrganisationUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None


class OrganisationRead(ORMModel):
    id: int
    name: str
    description: Optional[str] = None
    created_at: datetime


# --- Team ---
class TeamCreate(BaseModel):
    organisation_id: int
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None


class TeamUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None


class TeamRead(ORMModel):
    id: int
    organisation_id: int
    name: str
    description: Optional[str] = None
    created_at: datetime


# --- Agent ---
class AgentCreate(BaseModel):
    organisation_id: int
    name: str = Field(..., min_length=1, max_length=200)
    role: AgentRole
    team_id: Optional[int] = None
    is_human: bool = False
    system_prompt: Optional[str] = None


class AgentUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    role: Optional[AgentRole] = None
    team_id: Optional[int] = None
    is_human: Optional[bool] = None
    system_prompt: Optional[str] = None
    status: Optional[str] = None


class AgentRead(ORMModel):
    id: int
    organisation_id: int
    team_id: Optional[int] = None
    name: str
    role: AgentRole
    is_human: bool
    system_prompt: Optional[str] = None
    status: Optional[str] = "idle"
    created_at: datetime


# --- Channel ---
class ChannelCreate(BaseModel):
    organisation_id: int
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None


class ChannelUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None


class ChannelRead(ORMModel):
    id: int
    organisation_id: int
    name: str
    description: Optional[str] = None
    created_at: datetime


# --- Message ---
class MessageCreate(BaseModel):
    channel_id: int
    agent_id: int
    content: str = Field(..., min_length=1)
    parent_id: Optional[int] = None


class MessageRead(ORMModel):
    id: int
    channel_id: int
    agent_id: int
    content: str
    parent_id: Optional[int] = None
    created_at: datetime
    agent_name: Optional[str] = None
    agent_role: Optional[AgentRole] = None


# --- Task ---
class TaskCreate(BaseModel):
    organisation_id: int
    title: str = Field(..., min_length=1, max_length=300)
    description: Optional[str] = None
    assignee_id: Optional[int] = None
    channel_id: Optional[int] = None
    parent_task_id: Optional[int] = None
    status: TaskStatus = TaskStatus.pending


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=300)
    description: Optional[str] = None
    status: Optional[TaskStatus] = None
    assignee_id: Optional[int] = None
    channel_id: Optional[int] = None
    parent_task_id: Optional[int] = None
    result: Optional[str] = None


class TaskRead(ORMModel):
    id: int
    organisation_id: int
    title: str
    description: Optional[str] = None
    status: TaskStatus
    assignee_id: Optional[int] = None
    channel_id: Optional[int] = None
    parent_task_id: Optional[int] = None
    result: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class TaskAssign(BaseModel):
    assignee_id: int
    channel_id: Optional[int] = None


class TaskHandoff(BaseModel):
    to_agent_id: int
    note: Optional[str] = None


# --- Approvals ---
class ApprovalCreate(BaseModel):
    organisation_id: int
    title: str = Field(..., min_length=1, max_length=300)
    description: Optional[str] = None
    requester_agent_id: Optional[int] = None
    related_task_id: Optional[int] = None


class ApprovalDecision(BaseModel):
    decision_note: Optional[str] = None


class ApprovalRead(ORMModel):
    id: int
    organisation_id: int
    requester_agent_id: Optional[int] = None
    title: str
    description: Optional[str] = None
    status: ApprovalStatus
    decision_note: Optional[str] = None
    related_task_id: Optional[int] = None
    created_at: datetime
    resolved_at: Optional[datetime] = None
    requester_name: Optional[str] = None


# --- Routines ---
class RoutineCreate(BaseModel):
    organisation_id: int
    name: str = Field(..., min_length=1, max_length=200)
    prompt: str = Field(..., min_length=1)
    cron: Optional[str] = None
    every_seconds: Optional[int] = Field(None, ge=5)
    target_agent_id: Optional[int] = None
    channel_id: Optional[int] = None
    enabled: bool = True


class RoutineUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    prompt: Optional[str] = None
    cron: Optional[str] = None
    every_seconds: Optional[int] = Field(None, ge=5)
    target_agent_id: Optional[int] = None
    channel_id: Optional[int] = None
    enabled: Optional[bool] = None


class RoutineRead(ORMModel):
    id: int
    organisation_id: int
    name: str
    prompt: str
    cron: Optional[str] = None
    every_seconds: Optional[int] = None
    target_agent_id: Optional[int] = None
    channel_id: Optional[int] = None
    enabled: bool
    last_run_at: Optional[datetime] = None
    created_at: datetime


# --- Connectors ---
class ConnectorEnable(BaseModel):
    enabled: bool = True


class ConnectorInvoke(BaseModel):
    payload: dict = Field(default_factory=dict)
