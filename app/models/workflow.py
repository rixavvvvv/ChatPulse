from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, Enum as SqlEnum, ForeignKey, Index, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class WorkflowStatus(str, Enum):
    draft = "draft"
    published = "published"
    archived = "archived"


class NodeType(str, Enum):
    trigger = "trigger"
    action = "action"
    condition = "condition"
    delay = "delay"
    split = "split"
    join = "join"


class ExecutionStatus(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"
    paused = "paused"


class WorkflowDefinition(Base):
    __tablename__ = "workflow_definitions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[WorkflowStatus] = mapped_column(
        SqlEnum(WorkflowStatus, name="workflow_status"),
        nullable=False,
        default=WorkflowStatus.draft,
    )
    definition: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )
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

    executions: Mapped[list["WorkflowExecution"]] = relationship(
        back_populates="definition",
        cascade="all, delete-orphan",
    )


class WorkflowNode(Base):
    __tablename__ = "workflow_nodes"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    workflow_definition_id: Mapped[int] = mapped_column(
        ForeignKey("workflow_definitions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    node_id: Mapped[str] = mapped_column(String(64), nullable=False)
    node_type: Mapped[NodeType] = mapped_column(
        SqlEnum(NodeType, name="workflow_node_type"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    config: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )
    position_x: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    position_y: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_workflow_nodes_definition_node", "workflow_definition_id", "node_id", unique=True),
    )


class WorkflowEdge(Base):
    __tablename__ = "workflow_edges"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    workflow_definition_id: Mapped[int] = mapped_column(
        ForeignKey("workflow_definitions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    edge_id: Mapped[str] = mapped_column(String(64), nullable=False)
    source_node_id: Mapped[str] = mapped_column(String(64), nullable=False)
    target_node_id: Mapped[str] = mapped_column(String(64), nullable=False)
    condition: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_workflow_edges_definition_source_target", "workflow_definition_id", "source_node_id", "target_node_id"),
    )


class WorkflowExecution(Base):
    __tablename__ = "workflow_executions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id"),
        nullable=False,
        index=True,
    )
    workflow_definition_id: Mapped[int] = mapped_column(
        ForeignKey("workflow_definitions.id"),
        nullable=False,
        index=True,
    )
    execution_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    status: Mapped[ExecutionStatus] = mapped_column(
        SqlEnum(ExecutionStatus, name="execution_status"),
        nullable=False,
        default=ExecutionStatus.pending,
    )
    trigger_data: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )
    context: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )
    current_node_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    definition: Mapped["WorkflowDefinition"] = relationship(back_populates="executions")
    node_executions: Mapped[list["NodeExecution"]] = relationship(
        back_populates="execution",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_workflow_executions_status", "workspace_id", "status"),
    )


class NodeExecution(Base):
    __tablename__ = "node_executions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    workflow_execution_id: Mapped[int] = mapped_column(
        ForeignKey("workflow_executions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    node_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    node_type: Mapped[NodeType] = mapped_column(
        SqlEnum(NodeType, name="node_execution_type"),
        nullable=False,
    )
    status: Mapped[ExecutionStatus] = mapped_column(
        SqlEnum(ExecutionStatus, name="node_execution_status"),
        nullable=False,
        default=ExecutionStatus.pending,
    )
    input_data: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )
    output_data: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    execution: Mapped["WorkflowExecution"] = relationship(back_populates="node_executions")

    __table_args__ = (
        Index("ix_node_executions_execution_node", "workflow_execution_id", "node_id"),
    )