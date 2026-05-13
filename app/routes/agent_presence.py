"""
Agent Presence API Routes
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db_session
from app.dependencies.auth import get_current_user
from app.dependencies.workspace import get_current_workspace
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.conversation import (
    AgentPresenceHeartbeat,
    AgentPresenceResponse,
)
from app.services import agent_presence_service

router = APIRouter(prefix="/presence", tags=["presence"])


@router.post("/heartbeat", response_model=AgentPresenceResponse)
async def heartbeat(
    payload: AgentPresenceHeartbeat,
    db: AsyncSession = Depends(get_db_session),
    workspace: Workspace = Depends(get_current_workspace),
    current_user: User = Depends(get_current_user),
):
    presence = await agent_presence_service.update_heartbeat(
        db, current_user.id, workspace.id,
        status=payload.status.value,
        metadata_json=payload.metadata_json,
    )
    return presence


@router.get("/agents", response_model=list[AgentPresenceResponse])
async def get_online_agents(
    db: AsyncSession = Depends(get_db_session),
    workspace: Workspace = Depends(get_current_workspace),
):
    agents = await agent_presence_service.get_all_agents_status(db, workspace.id)
    return agents
