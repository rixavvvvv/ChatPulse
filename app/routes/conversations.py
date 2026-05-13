"""
Conversations API Routes

Full REST API for the shared inbox conversation system.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db_session
from app.dependencies.auth import get_current_user
from app.dependencies.workspace import get_current_workspace
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.conversation import (
    ConversationAssignRequest,
    ConversationAssignmentResponse,
    ConversationCreate,
    ConversationLabelAssignRequest,
    ConversationLabelAssignmentResponse,
    ConversationLabelCreate,
    ConversationLabelResponse,
    ConversationListResponse,
    ConversationMessageCreate,
    ConversationMessageResponse,
    ConversationMetrics,
    ConversationNoteCreate,
    ConversationNoteResponse,
    ConversationResponse,
    ConversationStateTransition,
    ConversationUnreadResponse,
    ConversationUpdate,
    MarkReadRequest,
    UnreadSummaryResponse,
)
from app.models.conversation import ConversationStatus, ConversationChannel, ConversationPriority
from app.services import (
    conversation_service,
    conversation_message_service,
    conversation_assignment_service,
    conversation_note_service,
    conversation_label_service,
    conversation_unread_service,
    conversation_metrics_service,
)
from app.services.conversation_state_engine import (
    InvalidTransitionError,
    StaleVersionError,
    transition_state,
)

router = APIRouter(prefix="/conversations", tags=["conversations"])

# ──────────────────────────────────────────────────────────
# Conversations CRUD
# ──────────────────────────────────────────────────────────

@router.post("", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    payload: ConversationCreate,
    db: AsyncSession = Depends(get_db_session),
    workspace: Workspace = Depends(get_current_workspace),
):
    conv = await conversation_service.create_conversation(
        db,
        workspace_id=workspace.id,
        contact_id=payload.contact_id,
        channel=payload.channel.value,
        priority=payload.priority.value,
        subject=payload.subject,
        metadata_json=payload.metadata_json,
    )
    return conv


@router.get("", response_model=list[ConversationListResponse])
async def list_conversations(
    status_filter: str | None = Query(None, alias="status"),
    channel: str | None = None,
    priority: str | None = None,
    assigned_to: int | None = None,
    label_id: int | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db_session),
    workspace: Workspace = Depends(get_current_workspace),
    current_user: User = Depends(get_current_user),
):
    enriched, total = await conversation_service.list_conversations(
        db,
        workspace_id=workspace.id,
        status=status_filter,
        channel=channel,
        priority=priority,
        assigned_to=assigned_to,
        label_id=label_id,
        search=search,
        limit=limit,
        offset=offset,
        user_id=current_user.id,
    )

    results = []
    for item in enriched:
        conv = item["conversation"]
        results.append(ConversationListResponse(
            id=conv.id,
            workspace_id=conv.workspace_id,
            contact_id=conv.contact_id,
            channel=conv.channel,
            status=conv.status,
            priority=conv.priority,
            subject=conv.subject,
            last_message_preview=conv.last_message_preview,
            last_message_at=conv.last_message_at,
            unread_count=item["unread_count"],
            created_at=conv.created_at,
            updated_at=conv.updated_at,
        ))

    return results


@router.get("/metrics", response_model=ConversationMetrics)
async def get_metrics(
    db: AsyncSession = Depends(get_db_session),
    workspace: Workspace = Depends(get_current_workspace),
):
    metrics = await conversation_metrics_service.get_conversation_metrics(db, workspace.id)
    return ConversationMetrics(**metrics)


@router.get("/unread", response_model=UnreadSummaryResponse)
async def get_unread_summary(
    db: AsyncSession = Depends(get_db_session),
    workspace: Workspace = Depends(get_current_workspace),
    current_user: User = Depends(get_current_user),
):
    total = await conversation_unread_service.get_total_unread(db, current_user.id, workspace.id)
    unread_convs = await conversation_unread_service.get_unread_conversations(
        db, current_user.id, workspace.id
    )

    conversations = [
        ConversationUnreadResponse(
            conversation_id=state.conversation_id,
            unread_count=state.unread_count,
            last_read_at=state.last_read_at,
        )
        for state in unread_convs
    ]

    return UnreadSummaryResponse(
        total_unread=total,
        conversations=conversations,
    )


@router.get("/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: int,
    db: AsyncSession = Depends(get_db_session),
    workspace: Workspace = Depends(get_current_workspace),
):
    conv = await conversation_service.get_conversation_by_id(db, conversation_id, workspace.id)
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return conv


@router.patch("/{conversation_id}", response_model=ConversationResponse)
async def update_conversation(
    conversation_id: int,
    payload: ConversationUpdate,
    db: AsyncSession = Depends(get_db_session),
    workspace: Workspace = Depends(get_current_workspace),
):
    conv = await conversation_service.get_conversation_by_id(db, conversation_id, workspace.id)
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    updated = await conversation_service.update_conversation(
        db, conv,
        priority=payload.priority.value if payload.priority else None,
        subject=payload.subject,
        metadata_json=payload.metadata_json,
    )
    return updated


# ──────────────────────────────────────────────────────────
# State Transitions
# ──────────────────────────────────────────────────────────

@router.post("/{conversation_id}/assign", response_model=ConversationAssignmentResponse)
async def assign_conversation(
    conversation_id: int,
    payload: ConversationAssignRequest,
    db: AsyncSession = Depends(get_db_session),
    workspace: Workspace = Depends(get_current_workspace),
    current_user: User = Depends(get_current_user),
):
    conv = await conversation_service.get_conversation_by_id(db, conversation_id, workspace.id)
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    try:
        assignment = await conversation_assignment_service.assign_agent(
            db, conv, payload.agent_user_id, current_user.id, payload.version,
        )
        return assignment
    except StaleVersionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.post("/{conversation_id}/unassign", status_code=status.HTTP_204_NO_CONTENT)
async def unassign_conversation(
    conversation_id: int,
    payload: ConversationStateTransition,
    db: AsyncSession = Depends(get_db_session),
    workspace: Workspace = Depends(get_current_workspace),
    current_user: User = Depends(get_current_user),
):
    conv = await conversation_service.get_conversation_by_id(db, conversation_id, workspace.id)
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    try:
        await conversation_assignment_service.unassign_agent(
            db, conv, payload.version, current_user.id,
        )
    except (StaleVersionError, InvalidTransitionError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.post("/{conversation_id}/resolve", response_model=ConversationResponse)
async def resolve_conversation(
    conversation_id: int,
    payload: ConversationStateTransition,
    db: AsyncSession = Depends(get_db_session),
    workspace: Workspace = Depends(get_current_workspace),
    current_user: User = Depends(get_current_user),
):
    conv = await conversation_service.get_conversation_by_id(db, conversation_id, workspace.id)
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    try:
        return await transition_state(
            db, conv, ConversationStatus.resolved, payload.version, current_user.id,
        )
    except (StaleVersionError, InvalidTransitionError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.post("/{conversation_id}/reopen", response_model=ConversationResponse)
async def reopen_conversation(
    conversation_id: int,
    payload: ConversationStateTransition,
    db: AsyncSession = Depends(get_db_session),
    workspace: Workspace = Depends(get_current_workspace),
    current_user: User = Depends(get_current_user),
):
    conv = await conversation_service.get_conversation_by_id(db, conversation_id, workspace.id)
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    try:
        return await transition_state(
            db, conv, ConversationStatus.open, payload.version, current_user.id,
        )
    except (StaleVersionError, InvalidTransitionError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.post("/{conversation_id}/close", response_model=ConversationResponse)
async def close_conversation(
    conversation_id: int,
    payload: ConversationStateTransition,
    db: AsyncSession = Depends(get_db_session),
    workspace: Workspace = Depends(get_current_workspace),
    current_user: User = Depends(get_current_user),
):
    conv = await conversation_service.get_conversation_by_id(db, conversation_id, workspace.id)
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    try:
        return await transition_state(
            db, conv, ConversationStatus.closed, payload.version, current_user.id,
        )
    except (StaleVersionError, InvalidTransitionError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


# ──────────────────────────────────────────────────────────
# Messages
# ──────────────────────────────────────────────────────────

@router.get("/{conversation_id}/messages", response_model=list[ConversationMessageResponse])
async def list_messages(
    conversation_id: int,
    limit: int = 50,
    before_id: int | None = None,
    after_id: int | None = None,
    db: AsyncSession = Depends(get_db_session),
    workspace: Workspace = Depends(get_current_workspace),
):
    conv = await conversation_service.get_conversation_by_id(db, conversation_id, workspace.id)
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    messages = await conversation_message_service.list_messages(
        db, conversation_id, workspace.id,
        limit=limit, before_id=before_id, after_id=after_id,
    )
    return messages


@router.post("/{conversation_id}/messages", response_model=ConversationMessageResponse, status_code=status.HTTP_201_CREATED)
async def send_message(
    conversation_id: int,
    payload: ConversationMessageCreate,
    db: AsyncSession = Depends(get_db_session),
    workspace: Workspace = Depends(get_current_workspace),
    current_user: User = Depends(get_current_user),
):
    conv = await conversation_service.get_conversation_by_id(db, conversation_id, workspace.id)
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    message = await conversation_message_service.create_outbound_message(
        db, conversation_id, workspace.id, current_user.id,
        content=payload.content,
        content_type=payload.content_type.value,
        metadata_json=payload.metadata_json,
    )
    return message


# ──────────────────────────────────────────────────────────
# Internal Notes
# ──────────────────────────────────────────────────────────

@router.get("/{conversation_id}/notes", response_model=list[ConversationNoteResponse])
async def list_notes(
    conversation_id: int,
    db: AsyncSession = Depends(get_db_session),
    workspace: Workspace = Depends(get_current_workspace),
):
    return await conversation_note_service.list_notes(db, conversation_id, workspace.id)


@router.post("/{conversation_id}/notes", response_model=ConversationNoteResponse, status_code=status.HTTP_201_CREATED)
async def create_note(
    conversation_id: int,
    payload: ConversationNoteCreate,
    db: AsyncSession = Depends(get_db_session),
    workspace: Workspace = Depends(get_current_workspace),
    current_user: User = Depends(get_current_user),
):
    return await conversation_note_service.create_note(
        db, conversation_id, workspace.id, current_user.id, payload.body,
    )


@router.delete("/{conversation_id}/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note(
    conversation_id: int,
    note_id: int,
    db: AsyncSession = Depends(get_db_session),
    workspace: Workspace = Depends(get_current_workspace),
):
    result = await conversation_note_service.delete_note(db, note_id, conversation_id, workspace.id)
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")


# ──────────────────────────────────────────────────────────
# Labels
# ──────────────────────────────────────────────────────────

@router.get("/{conversation_id}/labels", response_model=list[ConversationLabelResponse])
async def get_conversation_labels(
    conversation_id: int,
    db: AsyncSession = Depends(get_db_session),
    workspace: Workspace = Depends(get_current_workspace),
):
    return await conversation_label_service.get_conversation_labels(db, conversation_id, workspace.id)


@router.post("/{conversation_id}/labels", response_model=ConversationLabelAssignmentResponse, status_code=status.HTTP_201_CREATED)
async def add_label(
    conversation_id: int,
    payload: ConversationLabelAssignRequest,
    db: AsyncSession = Depends(get_db_session),
    workspace: Workspace = Depends(get_current_workspace),
):
    try:
        return await conversation_label_service.assign_label(
            db, conversation_id, payload.label_id, workspace.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.delete("/{conversation_id}/labels/{label_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_label(
    conversation_id: int,
    label_id: int,
    db: AsyncSession = Depends(get_db_session),
    workspace: Workspace = Depends(get_current_workspace),
):
    removed = await conversation_label_service.unassign_label(db, conversation_id, label_id)
    if not removed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Label assignment not found")


# ──────────────────────────────────────────────────────────
# Mark Read
# ──────────────────────────────────────────────────────────

@router.post("/{conversation_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_read(
    conversation_id: int,
    payload: MarkReadRequest | None = None,
    db: AsyncSession = Depends(get_db_session),
    workspace: Workspace = Depends(get_current_workspace),
    current_user: User = Depends(get_current_user),
):
    await conversation_unread_service.mark_conversation_read(
        db, conversation_id, current_user.id, workspace.id,
        last_read_message_id=payload.last_read_message_id if payload else None,
    )


# ──────────────────────────────────────────────────────────
# Workspace Labels Management
# ──────────────────────────────────────────────────────────

labels_router = APIRouter(prefix="/conversation-labels", tags=["conversation-labels"])


@labels_router.get("", response_model=list[ConversationLabelResponse])
async def list_workspace_labels(
    db: AsyncSession = Depends(get_db_session),
    workspace: Workspace = Depends(get_current_workspace),
):
    return await conversation_label_service.list_labels(db, workspace.id)


@labels_router.post("", response_model=ConversationLabelResponse, status_code=status.HTTP_201_CREATED)
async def create_workspace_label(
    payload: ConversationLabelCreate,
    db: AsyncSession = Depends(get_db_session),
    workspace: Workspace = Depends(get_current_workspace),
):
    return await conversation_label_service.create_label(
        db, workspace.id, payload.name, payload.color, payload.description,
    )


@labels_router.delete("/{label_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workspace_label(
    label_id: int,
    db: AsyncSession = Depends(get_db_session),
    workspace: Workspace = Depends(get_current_workspace),
):
    deleted = await conversation_label_service.delete_label(db, label_id, workspace.id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Label not found")
