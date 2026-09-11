"""Pydantic v2 request/response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from grok_org_os.models import AgentRole, TaskStatus


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


class AgentRead(ORMModel):
    id: int
    organisation_id: int
    team_id: Optional[int] = None
    name: str
    role: AgentRole
    is_human: bool
    system_prompt: Optional[str] = None
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


class MessageRead(ORMModel):
    id: int
    channel_id: int
    agent_id: int
    content: str
    created_at: datetime


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
