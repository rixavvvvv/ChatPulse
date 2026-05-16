from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import desc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db_session
from app.dependencies.auth import require_super_admin
from app.models.queue_dead_letter import QueueDeadLetter
from app.models.user import User
from app.schemas.admin import (
    AdminCreateUserRequest,
    AdminPlanCreateRequest,
    AdminPlanResponse,
    AdminUserActivationUpdateRequest,
    AdminUserResponse,
    AdminUserRoleUpdateRequest,
    AdminUserSubscriptionUpdateRequest,
    AdminWorkspaceResponse,
    AdminWorkspaceUsageResponse,
)
from app.schemas.webhooks_admin import (
    WebhookIngestionReplayRequest,
    WebhookIngestionReplayResponse,
    WebhookIngestionReplayItemResponse,
)
from app.services.admin_service import list_all_workspaces, list_workspace_usage_messages_sent
from app.services.auth_service import hash_password
from app.services.queue_monitoring_service import celery_inspect_snapshot
from app.services.subscription_service import (
    create_plan,
    get_plan_by_id,
    get_plan_by_name,
    get_user_subscription,
    list_plans,
    upsert_user_subscription,
)
from app.services.webhook_ingestion_service import replay_webhook_ingestions
from app.services.system_health_service import get_system_health_summary
from app.services.user_service import (
    create_user,
    get_user_by_email,
    get_user_by_id,
    list_users,
    update_user_active_status,
    update_user_role,
    update_user_subscription_plan,
)
from app.services.workspace_service import (
    build_default_workspace_name,
    create_workspace_with_owner_membership,
)

router = APIRouter(prefix="/admin", tags=["Admin"])


async def _build_admin_user_response(
    session: AsyncSession,
    user: User,
) -> AdminUserResponse:
    subscription = await get_user_subscription(session=session, user_id=user.id)
    return AdminUserResponse(
        id=user.id,
        email=user.email,
        role=user.role,
        subscription_plan=user.subscription_plan,
        is_active=user.is_active,
        plan_id=(subscription.plan_id if subscription else None),
        subscription_status=(subscription.status if subscription else None),
        created_at=user.created_at,
    )


@router.post("/users", response_model=AdminUserResponse, status_code=status.HTTP_201_CREATED)
async def create_user_as_super_admin(
    payload: AdminCreateUserRequest,
    session: AsyncSession = Depends(get_db_session),
    _super_admin: User = Depends(require_super_admin),
) -> AdminUserResponse:
    existing = await get_user_by_email(session=session, email=payload.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    normalized_plan_name = payload.subscription_plan.strip().lower()

    try:
        user = await create_user(
            session=session,
            email=payload.email,
            password_hash=hash_password(payload.password),
            role=payload.role,
            subscription_plan=normalized_plan_name,
            is_active=payload.is_active,
        )
        await create_workspace_with_owner_membership(
            session=session,
            name=build_default_workspace_name(payload.email),
            owner_id=user.id,
        )

        plan = await get_plan_by_name(
            session=session,
            name=normalized_plan_name,
        )
        if plan is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Plan not found",
            )
        await upsert_user_subscription(
            session=session,
            user_id=user.id,
            plan_id=plan.id,
        )
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    return await _build_admin_user_response(session=session, user=user)


@router.get("/users", response_model=list[AdminUserResponse])
async def list_users_as_super_admin(
    session: AsyncSession = Depends(get_db_session),
    _super_admin: User = Depends(require_super_admin),
) -> list[AdminUserResponse]:
    users = await list_users(session=session)
    return [
        await _build_admin_user_response(session=session, user=user)
        for user in users
    ]


@router.get("/plans", response_model=list[AdminPlanResponse])
async def list_plans_as_super_admin(
    session: AsyncSession = Depends(get_db_session),
    _super_admin: User = Depends(require_super_admin),
) -> list[AdminPlanResponse]:
    plans = await list_plans(session=session)
    return [AdminPlanResponse.model_validate(plan) for plan in plans]


@router.post("/plans", response_model=AdminPlanResponse, status_code=status.HTTP_201_CREATED)
async def create_plan_as_super_admin(
    payload: AdminPlanCreateRequest,
    session: AsyncSession = Depends(get_db_session),
    _super_admin: User = Depends(require_super_admin),
) -> AdminPlanResponse:
    normalized_name = payload.name.strip().lower()
    existing = await get_plan_by_name(session=session, name=normalized_name)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Plan already exists",
        )

    try:
        plan = await create_plan(
            session=session,
            name=normalized_name,
            message_limit=payload.message_limit,
            price=float(payload.price),
        )
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Plan already exists",
        )

    return AdminPlanResponse.model_validate(plan)


@router.patch("/users/{user_id}/subscription", response_model=AdminUserResponse)
async def update_user_subscription_as_super_admin(
    user_id: int,
    payload: AdminUserSubscriptionUpdateRequest,
    session: AsyncSession = Depends(get_db_session),
    _super_admin: User = Depends(require_super_admin),
) -> AdminUserResponse:
    user = await get_user_by_id(session=session, user_id=user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    plan = await get_plan_by_id(
        session=session,
        plan_id=payload.plan_id,
    )
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plan not found",
        )

    user = await update_user_subscription_plan(
        session=session,
        user=user,
        subscription_plan=plan.name,
    )

    await upsert_user_subscription(
        session=session,
        user_id=user.id,
        plan_id=plan.id,
        status=payload.status,
    )
    return await _build_admin_user_response(session=session, user=user)


@router.patch("/users/{user_id}/status", response_model=AdminUserResponse)
async def update_user_status_as_super_admin(
    user_id: int,
    payload: AdminUserActivationUpdateRequest,
    session: AsyncSession = Depends(get_db_session),
    _super_admin: User = Depends(require_super_admin),
) -> AdminUserResponse:
    user = await get_user_by_id(session=session, user_id=user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    user = await update_user_active_status(
        session=session,
        user=user,
        is_active=payload.is_active,
    )
    return await _build_admin_user_response(session=session, user=user)


@router.patch("/users/{user_id}/role", response_model=AdminUserResponse)
async def update_user_role_as_super_admin(
    user_id: int,
    payload: AdminUserRoleUpdateRequest,
    session: AsyncSession = Depends(get_db_session),
    _super_admin: User = Depends(require_super_admin),
) -> AdminUserResponse:
    user = await get_user_by_id(session=session, user_id=user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    user = await update_user_role(
        session=session,
        user=user,
        role=payload.role,
    )
    return await _build_admin_user_response(session=session, user=user)


@router.get("/workspaces", response_model=list[AdminWorkspaceResponse])
async def list_workspaces_as_super_admin(
    session: AsyncSession = Depends(get_db_session),
    _super_admin: User = Depends(require_super_admin),
) -> list[AdminWorkspaceResponse]:
    workspaces = await list_all_workspaces(session=session)
    return [
        AdminWorkspaceResponse(
            id=workspace.id,
            name=workspace.name,
            owner_id=workspace.owner_id,
            created_at=workspace.created_at,
        )
        for workspace in workspaces
    ]


@router.get("/usage/messages", response_model=list[AdminWorkspaceUsageResponse])
async def monitor_messages_sent_as_super_admin(
    session: AsyncSession = Depends(get_db_session),
    _super_admin: User = Depends(require_super_admin),
) -> list[AdminWorkspaceUsageResponse]:
    usage_rows = await list_workspace_usage_messages_sent(session=session)
    return [
        AdminWorkspaceUsageResponse(
            workspace_id=workspace.id,
            workspace_name=workspace.name,
            owner_id=workspace.owner_id,
            messages_sent=usage.messages_sent,
            billing_cycle=usage.billing_cycle,
        )
        for workspace, usage in usage_rows
    ]


@router.get("/queues/inspect")
async def inspect_celery_queues(
    _super_admin: User = Depends(require_super_admin),
) -> dict:
    """Live worker snapshot (requires at least one reachable Celery worker)."""
    return celery_inspect_snapshot()


@router.get("/queues/dead-letters")
async def list_queue_dead_letters(
    session: AsyncSession = Depends(get_db_session),
    _super_admin: User = Depends(require_super_admin),
    limit: int = 50,
) -> list[dict]:
    cap = max(1, min(limit, 200))
    stmt = (
        select(QueueDeadLetter)
        .order_by(desc(QueueDeadLetter.id))
        .limit(cap)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [
        {
            "id": r.id,
            "task_name": r.task_name,
            "celery_task_id": r.celery_task_id,
            "exception_type": r.exception_type,
            "exception_message": r.exception_message,
            "retries_at_failure": r.retries_at_failure,
            "max_retries": r.max_retries,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "replayed_at": r.replayed_at.isoformat() if r.replayed_at else None,
        }
        for r in rows
    ]


@router.post(
    "/queues/webhook-ingestions/replay",
    response_model=WebhookIngestionReplayResponse,
)
async def replay_webhook_ingestions_admin(
    payload: WebhookIngestionReplayRequest,
    session: AsyncSession = Depends(get_db_session),
    _super_admin: User = Depends(require_super_admin),
) -> WebhookIngestionReplayResponse:
    raw = await replay_webhook_ingestions(
        session, ingestion_ids=payload.ingestion_ids
    )
    items: list[WebhookIngestionReplayItemResponse] = []
    for row in raw:
        items.append(
            WebhookIngestionReplayItemResponse(
                ingestion_id=int(row["ingestion_id"]),
                status=row.get("status"),
                celery_task_id=row.get("celery_task_id"),
                replay_count=row.get("replay_count"),
                error=row.get("error"),
            )
        )
    return WebhookIngestionReplayResponse(results=items)


@router.get("/system-health")
async def get_system_health(
    session: AsyncSession = Depends(get_db_session),
    _super_admin: User = Depends(require_super_admin),
) -> dict:
    """Get system health summary including Redis, PostgreSQL, Celery, WebSocket, queues."""
    return await get_system_health_summary(session)
