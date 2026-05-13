from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db_session
from app.dependencies.auth import get_current_user
from app.dependencies.workspace import get_workspace_id
from app.schemas.ecommerce_automation import (
    EcommerceAutomationCreate,
    EcommerceAutomationUpdate,
    EcommerceAutomationResponse,
    EcommerceAutomationListResponse,
    EcommerceAutomationExecutionResponse,
    EcommerceAutomationStats,
    AutomationExecutionStats,
    RecoveryMetrics,
)
from app.services import ecommerce_automation_service
from app.models.user import User

router = APIRouter(prefix="/ecommerce/automations", tags=["ecommerce-automations"])


@router.post("", response_model=EcommerceAutomationResponse, status_code=status.HTTP_201_CREATED)
async def create_automation(
    automation_data: EcommerceAutomationCreate,
    db: AsyncSession = Depends(get_db_session),
    workspace_id: int = Depends(get_workspace_id),
    current_user: User = Depends(get_current_user),
):
    automation = await ecommerce_automation_service.create_automation(
        db,
        workspace_id=workspace_id,
        name=automation_data.name,
        description=automation_data.description,
        automation_type=automation_data.automation_type.value,
        trigger_config=automation_data.trigger_config.model_dump(),
        action_config=automation_data.action_config.model_dump(),
        delay_seconds=automation_data.delay_seconds,
        delay_type=automation_data.delay_type,
        segment_id=automation_data.segment_id,
        template_id=automation_data.template_id,
        priority=automation_data.priority,
        max_retries=automation_data.max_retries,
        created_by=current_user.id,
    )
    return automation


@router.get("", response_model=list[EcommerceAutomationListResponse])
async def list_automations(
    automation_type: str | None = None,
    trigger_type: str | None = None,
    status_filter: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db_session),
    workspace_id: int = Depends(get_workspace_id),
):
    automations, total = await ecommerce_automation_service.list_automations(
        db,
        workspace_id,
        automation_type=automation_type,
        trigger_type=trigger_type,
        status=status_filter,
        limit=limit,
        offset=offset,
    )
    return automations


@router.get("/stats", response_model=EcommerceAutomationStats)
async def get_automation_stats(
    db: AsyncSession = Depends(get_db_session),
    workspace_id: int = Depends(get_workspace_id),
):
    stats = await ecommerce_automation_service.get_automation_stats(db, workspace_id)

    recovery = await ecommerce_automation_service.get_abandoned_cart_recovery_metrics(db, workspace_id)

    return EcommerceAutomationStats(
        total_automations=stats.get("total_automations", 0),
        active_automations=stats.get("active_automations", 0),
        paused_automations=stats.get("paused_automations", 0),
        total_executions=stats.get("total_executions", 0),
        sent_count=stats.get("sent_count", 0),
        delivered_count=stats.get("delivered_count", 0),
        failed_count=stats.get("failed_count", 0),
        conversion_count=recovery.get("recovered_orders", 0),
        total_revenue=0,
        avg_recovery_rate=recovery.get("recovery_rate"),
        avg_conversion_rate=None,
    )


@router.get("/recovery-metrics", response_model=RecoveryMetrics)
async def get_recovery_metrics(
    days: int = 30,
    db: AsyncSession = Depends(get_db_session),
    workspace_id: int = Depends(get_workspace_id),
):
    metrics = await ecommerce_automation_service.get_abandoned_cart_recovery_metrics(
        db, workspace_id, days
    )
    return RecoveryMetrics(
        carts_abandoned=metrics.get("carts_abandoned", 0),
        recovery_attempts=metrics.get("recovery_attempts", 0),
        recovered_orders=metrics.get("recovered_orders", 0),
        recovery_rate=metrics.get("recovery_rate", 0),
        revenue_recovered=0,
        avg_recovery_time_hours=None,
    )


@router.get("/{automation_id}", response_model=EcommerceAutomationResponse)
async def get_automation(
    automation_id: int,
    db: AsyncSession = Depends(get_db_session),
    workspace_id: int = Depends(get_workspace_id),
):
    automation = await ecommerce_automation_service.get_automation_by_id(
        db, automation_id, workspace_id
    )
    if not automation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Automation not found")
    return automation


@router.patch("/{automation_id}", response_model=EcommerceAutomationResponse)
async def update_automation(
    automation_id: int,
    automation_data: EcommerceAutomationUpdate,
    db: AsyncSession = Depends(get_db_session),
    workspace_id: int = Depends(get_workspace_id),
):
    automation = await ecommerce_automation_service.get_automation_by_id(
        db, automation_id, workspace_id
    )
    if not automation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Automation not found")

    updated = await ecommerce_automation_service.update_automation(
        db,
        automation,
        name=automation_data.name,
        description=automation_data.description,
        status=automation_data.status.value if automation_data.status else None,
        trigger_config=automation_data.trigger_config.model_dump() if automation_data.trigger_config else None,
        action_config=automation_data.action_config.model_dump() if automation_data.action_config else None,
        delay_seconds=automation_data.delay_seconds,
        delay_type=automation_data.delay_type,
        segment_id=automation_data.segment_id,
        template_id=automation_data.template_id,
        priority=automation_data.priority,
        max_retries=automation_data.max_retries,
    )
    return updated


@router.delete("/{automation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_automation(
    automation_id: int,
    db: AsyncSession = Depends(get_db_session),
    workspace_id: int = Depends(get_workspace_id),
):
    automation = await ecommerce_automation_service.get_automation_by_id(
        db, automation_id, workspace_id
    )
    if not automation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Automation not found")

    await ecommerce_automation_service.delete_automation(db, automation)


executions_router = APIRouter(prefix="/ecommerce/automations/{automation_id}/executions", tags=["automation-executions"])


@executions_router.get("", response_model=list[EcommerceAutomationExecutionResponse])
async def list_automation_executions(
    automation_id: int,
    status_filter: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db_session),
    workspace_id: int = Depends(get_workspace_id),
):
    automation = await ecommerce_automation_service.get_automation_by_id(
        db, automation_id, workspace_id
    )
    if not automation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Automation not found")

    executions, total = await ecommerce_automation_service.list_executions(
        db,
        workspace_id,
        automation_id=automation_id,
        status=status_filter,
        limit=limit,
        offset=offset,
    )
    return executions


all_executions_router = APIRouter(prefix="/ecommerce/executions", tags=["ecommerce-executions"])


@all_executions_router.get("", response_model=list[EcommerceAutomationExecutionResponse])
async def list_all_executions(
    automation_id: int | None = None,
    status_filter: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db_session),
    workspace_id: int = Depends(get_workspace_id),
):
    executions, total = await ecommerce_automation_service.list_executions(
        db,
        workspace_id,
        automation_id=automation_id,
        status=status_filter,
        limit=limit,
        offset=offset,
    )
    return executions


@all_executions_router.get("/{execution_id}", response_model=EcommerceAutomationExecutionResponse)
async def get_execution(
    execution_id: str,
    db: AsyncSession = Depends(get_db_session),
    workspace_id: int = Depends(get_workspace_id),
):
    execution = await ecommerce_automation_service.get_execution(db, execution_id, workspace_id)
    if not execution:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution not found")
    return execution


# ─── Workflow Templates ────────────────────────────────────────────────

templates_router = APIRouter(prefix="/ecommerce/automation-templates", tags=["ecommerce-templates"])


@templates_router.get("")
async def list_automation_templates():
    """List all available pre-built ecommerce automation templates."""
    from app.services.ecommerce_workflow_templates import get_all_templates
    return get_all_templates()


@templates_router.get("/{template_key}")
async def get_automation_template(template_key: str):
    """Get a specific automation template by key."""
    from app.services.ecommerce_workflow_templates import get_template_by_key
    template = get_template_by_key(template_key)
    if not template:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    return template