"""
Shared Inbox — Conversation Schemas

Pydantic request/response models for the conversation system.
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ──────────────────────────────────────────────────────────
# Enums (mirror model enums for schema layer)
# ──────────────────────────────────────────────────────────

class ConversationStatus(str, Enum):
    open = "open"
    assigned = "assigned"
    resolved = "resolved"
    closed = "closed"


class ConversationPriority(str, Enum):
    low = "low"
    normal = "normal"
    high = "high"
    urgent = "urgent"


class ConversationChannel(str, Enum):
    whatsapp = "whatsapp"
    sms = "sms"
    email = "email"
    web = "web"


class MessageDirection(str, Enum):
    inbound = "inbound"
    outbound = "outbound"


class MessageSenderType(str, Enum):
    contact = "contact"
    agent = "agent"
    system = "system"
    bot = "bot"


class MessageContentType(str, Enum):
    text = "text"
    image = "image"
    video = "video"
    document = "document"
    audio = "audio"
    location = "location"
    template = "template"
    interactive = "interactive"
    system = "system"


class AgentPresenceStatus(str, Enum):
    online = "online"
    away = "away"
    busy = "busy"
    offline = "offline"


# ──────────────────────────────────────────────────────────
# Conversation Schemas
# ──────────────────────────────────────────────────────────

class ConversationCreate(BaseModel):
    contact_id: int
    channel: ConversationChannel = ConversationChannel.whatsapp
    priority: ConversationPriority = ConversationPriority.normal
    subject: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ConversationUpdate(BaseModel):
    priority: ConversationPriority | None = None
    subject: str | None = None
    metadata_json: dict[str, Any] | None = None


class ConversationResponse(BaseModel):
    id: int
    workspace_id: int
    contact_id: int
    channel: ConversationChannel
    status: ConversationStatus
    priority: ConversationPriority
    subject: str | None
    last_message_preview: str | None
    last_message_at: datetime | None
    version: int
    metadata_json: dict[str, Any]
    resolved_at: datetime | None
    closed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ConversationListResponse(BaseModel):
    id: int
    workspace_id: int
    contact_id: int
    channel: ConversationChannel
    status: ConversationStatus
    priority: ConversationPriority
    subject: str | None
    last_message_preview: str | None
    last_message_at: datetime | None
    unread_count: int = 0
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ConversationStateTransition(BaseModel):
    """Used for assign/resolve/close/reopen actions."""
    version: int = Field(..., description="Current version for optimistic locking")


# ──────────────────────────────────────────────────────────
# Message Schemas
# ──────────────────────────────────────────────────────────

class ConversationMessageCreate(BaseModel):
    content: str
    content_type: MessageContentType = MessageContentType.text
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ConversationMessageResponse(BaseModel):
    id: int
    conversation_id: int
    workspace_id: int
    direction: MessageDirection
    sender_type: MessageSenderType
    sender_id: int | None
    content_type: MessageContentType
    content: str
    provider_message_id: str | None
    metadata_json: dict[str, Any]
    created_at: datetime

    class Config:
        from_attributes = True


# ──────────────────────────────────────────────────────────
# Assignment Schemas
# ──────────────────────────────────────────────────────────

class ConversationAssignRequest(BaseModel):
    agent_user_id: int
    version: int = Field(..., description="Current conversation version for optimistic locking")


class ConversationAssignmentResponse(BaseModel):
    id: int
    conversation_id: int
    agent_user_id: int
    assigned_by: int | None
    is_active: bool
    assigned_at: datetime
    unassigned_at: datetime | None

    class Config:
        from_attributes = True


# ──────────────────────────────────────────────────────────
# Internal Note Schemas
# ──────────────────────────────────────────────────────────

class ConversationNoteCreate(BaseModel):
    body: str


class ConversationNoteResponse(BaseModel):
    id: int
    conversation_id: int
    author_user_id: int
    body: str
    deleted_at: datetime | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ──────────────────────────────────────────────────────────
# Label Schemas
# ──────────────────────────────────────────────────────────

class ConversationLabelCreate(BaseModel):
    name: str = Field(..., max_length=128)
    color: str = Field("#6B7280", max_length=7)
    description: str | None = None


class ConversationLabelResponse(BaseModel):
    id: int
    workspace_id: int
    name: str
    color: str
    description: str | None
    created_at: datetime

    class Config:
        from_attributes = True


class ConversationLabelAssignRequest(BaseModel):
    label_id: int


class ConversationLabelAssignmentResponse(BaseModel):
    id: int
    conversation_id: int
    label_id: int
    created_at: datetime

    class Config:
        from_attributes = True


# ──────────────────────────────────────────────────────────
# Unread State Schemas
# ──────────────────────────────────────────────────────────

class ConversationUnreadResponse(BaseModel):
    conversation_id: int
    unread_count: int
    last_read_at: datetime | None


class UnreadSummaryResponse(BaseModel):
    total_unread: int
    conversations: list[ConversationUnreadResponse]


class MarkReadRequest(BaseModel):
    last_read_message_id: int | None = None


# ──────────────────────────────────────────────────────────
# Agent Presence Schemas
# ──────────────────────────────────────────────────────────

class AgentPresenceHeartbeat(BaseModel):
    status: AgentPresenceStatus = AgentPresenceStatus.online
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class AgentPresenceResponse(BaseModel):
    user_id: int
    workspace_id: int
    status: AgentPresenceStatus
    last_heartbeat_at: datetime

    class Config:
        from_attributes = True


# ──────────────────────────────────────────────────────────
# WebSocket Event Schemas
# ──────────────────────────────────────────────────────────

class WebSocketEvent(BaseModel):
    """Base WebSocket event structure."""
    event_type: str
    workspace_id: int
    timestamp: datetime
    payload: dict[str, Any] = Field(default_factory=dict)


class TypingEvent(BaseModel):
    conversation_id: int
    user_id: int
    is_typing: bool


class PresenceEvent(BaseModel):
    user_id: int
    status: AgentPresenceStatus


class UnreadUpdateEvent(BaseModel):
    conversation_id: int
    unread_count: int


# ──────────────────────────────────────────────────────────
# Metrics Schemas
# ──────────────────────────────────────────────────────────

class ConversationMetrics(BaseModel):
    total_conversations: int
    open_conversations: int
    assigned_conversations: int
    resolved_conversations: int
    closed_conversations: int
    avg_response_time_seconds: float | None
    avg_resolution_time_seconds: float | None
    total_messages: int
    inbound_messages: int
    outbound_messages: int


class AgentWorkloadResponse(BaseModel):
    user_id: int
    active_conversations: int
    resolved_today: int
    avg_response_time_seconds: float | None
