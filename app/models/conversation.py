"""
Shared Inbox — Conversation Models

Core database models for the conversation/inbox system.
Includes conversations, messages, assignments, notes, labels, unread state, and agent presence.
"""

from datetime import datetime
from enum import Enum

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SqlEnum,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


# ──────────────────────────────────────────────────────────
# Enums
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
# Conversation
# ──────────────────────────────────────────────────────────

class Conversation(Base):
    """
    Core conversation entity.

    Each conversation links a workspace to a contact via a channel.
    Optimistic locking via `version` column to prevent concurrent state changes.
    """

    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id"),
        nullable=False,
        index=True,
    )
    contact_id: Mapped[int] = mapped_column(
        ForeignKey("contacts.id"),
        nullable=False,
        index=True,
    )

    channel: Mapped[ConversationChannel] = mapped_column(
        SqlEnum(ConversationChannel, name="conversation_channel"),
        nullable=False,
        default=ConversationChannel.whatsapp,
    )
    status: Mapped[ConversationStatus] = mapped_column(
        SqlEnum(ConversationStatus, name="conversation_status"),
        nullable=False,
        default=ConversationStatus.open,
    )
    priority: Mapped[ConversationPriority] = mapped_column(
        SqlEnum(ConversationPriority, name="conversation_priority"),
        nullable=False,
        default=ConversationPriority.normal,
    )

    subject: Mapped[str | None] = mapped_column(String(512), nullable=True)
    last_message_preview: Mapped[str | None] = mapped_column(String(512), nullable=True)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Optimistic locking version
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    messages: Mapped[list["ConversationMessage"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="ConversationMessage.created_at",
    )
    assignments: Mapped[list["ConversationAssignment"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
    )
    notes: Mapped[list["ConversationInternalNote"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
    )
    label_assignments: Mapped[list["ConversationLabelAssignment"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
    )
    unread_states: Mapped[list["ConversationUnreadState"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_conversations_workspace_status", "workspace_id", "status"),
        Index("ix_conversations_workspace_contact", "workspace_id", "contact_id"),
        Index("ix_conversations_last_message", "workspace_id", "last_message_at"),
    )


# ──────────────────────────────────────────────────────────
# Conversation Message
# ──────────────────────────────────────────────────────────

class ConversationMessage(Base):
    """
    Individual message within a conversation.

    Supports both inbound (from contact) and outbound (from agent/system) messages.
    Links to message_tracking via provider_message_id for delivery status.
    """

    __tablename__ = "conversation_messages"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id"),
        nullable=False,
        index=True,
    )

    direction: Mapped[MessageDirection] = mapped_column(
        SqlEnum(MessageDirection, name="message_direction"),
        nullable=False,
    )
    sender_type: Mapped[MessageSenderType] = mapped_column(
        SqlEnum(MessageSenderType, name="message_sender_type"),
        nullable=False,
    )
    sender_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)

    content_type: Mapped[MessageContentType] = mapped_column(
        SqlEnum(MessageContentType, name="message_content_type"),
        nullable=False,
        default=MessageContentType.text,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # Link to Meta message tracking
    provider_message_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)

    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")

    __table_args__ = (
        Index("ix_conversation_messages_conversation_created", "conversation_id", "created_at"),
        Index("ix_conversation_messages_provider", "provider_message_id"),
    )


# ──────────────────────────────────────────────────────────
# Conversation Assignment
# ──────────────────────────────────────────────────────────

class ConversationAssignment(Base):
    """
    Tracks agent assignments to conversations.

    Only one active assignment per conversation at a time.
    Historical assignments preserved for audit.
    """

    __tablename__ = "conversation_assignments"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id"),
        nullable=False,
        index=True,
    )
    agent_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    assigned_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    unassigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    conversation: Mapped["Conversation"] = relationship(back_populates="assignments")

    __table_args__ = (
        Index("ix_assignments_conversation_active", "conversation_id", "is_active"),
        Index("ix_assignments_agent_active", "agent_user_id", "is_active"),
    )


# ──────────────────────────────────────────────────────────
# Internal Notes
# ──────────────────────────────────────────────────────────

class ConversationInternalNote(Base):
    """
    Internal team notes on a conversation.
    Not visible to the contact. Soft-deletable.
    """

    __tablename__ = "conversation_internal_notes"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id"),
        nullable=False,
    )
    author_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)

    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    conversation: Mapped["Conversation"] = relationship(back_populates="notes")


# ──────────────────────────────────────────────────────────
# Labels
# ──────────────────────────────────────────────────────────

class ConversationLabel(Base):
    """Workspace-level label definition for conversations."""

    __tablename__ = "conversation_labels"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    color: Mapped[str] = mapped_column(String(7), nullable=False, default="#6B7280")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("workspace_id", "name", name="uq_conversation_label_workspace_name"),
    )


class ConversationLabelAssignment(Base):
    """Maps labels to conversations (many-to-many)."""

    __tablename__ = "conversation_label_assignments"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    label_id: Mapped[int] = mapped_column(
        ForeignKey("conversation_labels.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id"),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    conversation: Mapped["Conversation"] = relationship(back_populates="label_assignments")

    __table_args__ = (
        UniqueConstraint("conversation_id", "label_id", name="uq_conversation_label_assignment"),
    )


# ──────────────────────────────────────────────────────────
# Unread State
# ──────────────────────────────────────────────────────────

class ConversationUnreadState(Base):
    """
    Per-agent unread tracking per conversation.

    Updated when:
    - New message arrives → increment unread_count for all agents except sender
    - Agent reads conversation → reset unread_count, update last_read_*
    """

    __tablename__ = "conversation_unread_states"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id"),
        nullable=False,
    )

    unread_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_read_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    conversation: Mapped["Conversation"] = relationship(back_populates="unread_states")

    __table_args__ = (
        UniqueConstraint("conversation_id", "user_id", name="uq_unread_state_conversation_user"),
        Index("ix_unread_states_user_unread", "user_id", "unread_count"),
    )


# ──────────────────────────────────────────────────────────
# Agent Presence
# ──────────────────────────────────────────────────────────

class AgentPresence(Base):
    """
    Tracks online/offline/away status of agents.

    Updated via periodic heartbeats from WebSocket connections.
    Agents are considered offline if no heartbeat received within timeout.
    """

    __tablename__ = "agent_presence"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id"),
        nullable=False,
        index=True,
    )

    status: Mapped[AgentPresenceStatus] = mapped_column(
        SqlEnum(AgentPresenceStatus, name="agent_presence_status"),
        nullable=False,
        default=AgentPresenceStatus.offline,
    )

    last_heartbeat_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("user_id", "workspace_id", name="uq_agent_presence_user_workspace"),
        Index("ix_agent_presence_workspace_status", "workspace_id", "status"),
    )
