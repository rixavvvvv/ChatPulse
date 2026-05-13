import hashlib
import logging
import re
from datetime import datetime
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workflow import WorkflowDefinition
from app.models.workflow_trigger import (
    FilterType,
    TriggerExecutionStatus,
    WorkflowTrigger,
)

logger = logging.getLogger(__name__)


class TriggerMatchingEngine:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def find_matching_triggers(
        self,
        event_type: str,
        workspace_id: int,
        event_payload: dict[str, Any],
        correlation_id: str | None = None,
        trace_id: str | None = None,
    ) -> list[WorkflowTrigger]:
        stmt = (
            select(WorkflowTrigger)
            .options(
                selectinload(WorkflowTrigger.executions),
            )
            .where(
                and_(
                    WorkflowTrigger.workspace_id == workspace_id,
                    WorkflowTrigger.source == event_type,
                    WorkflowTrigger.status == "active",
                )
            )
        )
        result = await self.db.execute(stmt)
        triggers = list(result.scalars().all())

        matching_triggers = []
        for trigger in triggers:
            if await self._evaluate_filters(
                trigger,
                event_payload,
                correlation_id,
                trace_id,
                workspace_id,
            ):
                matching_triggers.append(trigger)

        matching_triggers.sort(key=lambda t: t.priority, reverse=True)
        return matching_triggers

    async def _evaluate_filters(
        self,
        trigger: WorkflowTrigger,
        event_payload: dict[str, Any],
        correlation_id: str | None,
        trace_id: str | None,
        workspace_id: int,
    ) -> bool:
        filters = trigger.filters
        if not filters:
            return True

        for filter_config in filters:
            filter_type = filter_config.get("filter_type")
            field = filter_config.get("field")
            operator = filter_config.get("operator")
            value = filter_config.get("value", {})

            if filter_type == FilterType.workspace:
                if not self._evaluate_workspace_filter(
                    workspace_id, operator, value
                ):
                    return False

            elif filter_type == FilterType.segment:
                if not await self._evaluate_segment_filter(
                    event_payload, operator, value
                ):
                    return False

            elif filter_type == FilterType.payload:
                if not self._evaluate_payload_filter(
                    event_payload, field, operator, value
                ):
                    return False

            elif filter_type == FilterType.metadata:
                if not self._evaluate_metadata_filter(
                    correlation_id, trace_id, event_payload, field, operator, value
                ):
                    return False

        return True

    def _evaluate_workspace_filter(
        self,
        workspace_id: int,
        operator: str,
        value: dict[str, Any],
    ) -> bool:
        target_workspace = value.get("workspace_id")
        if operator == "equals":
            return workspace_id == target_workspace
        elif operator == "not_equals":
            return workspace_id != target_workspace
        return True

    async def _evaluate_segment_filter(
        self,
        event_payload: dict[str, Any],
        operator: str,
        value: dict[str, Any],
    ) -> bool:
        contact_id = event_payload.get("contact_id")
        if not contact_id:
            return operator == "not_exists"

        segment_id = value.get("segment_id")
        if not segment_id:
            return True

        from app.models.contact_intelligence import SegmentMembership

        stmt = select(func.count()).where(
            and_(
                SegmentMembership.contact_id == contact_id,
                SegmentMembership.segment_id == segment_id,
            )
        )
        result = await self.db.execute(stmt)
        membership_count = result.scalar() or 0

        if operator == "in_segment":
            return membership_count > 0
        elif operator == "not_in_segment":
            return membership_count == 0
        return True

    def _evaluate_payload_filter(
        self,
        event_payload: dict[str, Any],
        field: str,
        operator: str,
        value: dict[str, Any],
    ) -> bool:
        field_value = self._get_nested_field(event_payload, field)
        target_value = value.get("value")

        if operator == "equals":
            return field_value == target_value
        elif operator == "not_equals":
            return field_value != target_value
        elif operator == "contains":
            return target_value in (field_value or "")
        elif operator == "not_contains":
            return target_value not in (field_value or "")
        elif operator == "exists":
            return field_value is not None
        elif operator == "not_exists":
            return field_value is None
        elif operator == "in_list":
            return field_value in (target_value or [])
        elif operator == "not_in_list":
            return field_value not in (target_value or [])
        elif operator == "greater_than":
            try:
                return float(field_value or 0) > float(target_value)
            except (TypeError, ValueError):
                return False
        elif operator == "less_than":
            try:
                return float(field_value or 0) < float(target_value)
            except (TypeError, ValueError):
                return False
        return True

    def _evaluate_metadata_filter(
        self,
        correlation_id: str | None,
        trace_id: str | None,
        event_payload: dict[str, Any],
        field: str,
        operator: str,
        value: dict[str, Any],
    ) -> bool:
        if field == "correlation_id":
            field_value = correlation_id
        elif field == "trace_id":
            field_value = trace_id
        else:
            field_value = event_payload.get(field)

        target_value = value.get("value")

        if operator == "equals":
            return field_value == target_value
        elif operator == "not_equals":
            return field_value != target_value
        elif operator == "exists":
            return field_value is not None
        elif operator == "not_exists":
            return field_value is None
        elif operator == "contains":
            return target_value in (field_value or "")
        return True

    def _get_nested_field(self, data: dict[str, Any], field_path: str) -> Any:
        keys = field_path.split(".")
        value = data
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
            else:
                return None
        return value


def generate_dedupe_key(
    event_type: str,
    workspace_id: int,
    event_payload: dict[str, Any],
    trigger_id: int,
) -> str:
    payload_str = str(sorted(event_payload.items()))
    payload_hash = hashlib.sha256(payload_str.encode()).hexdigest()[:16]
    return f"trigger:{event_type}:{workspace_id}:{trigger_id}:{payload_hash}"


def generate_event_dedupe_key(
    event_type: str,
    workspace_id: int,
    event_payload: dict[str, Any],
) -> str:
    payload_str = str(sorted(event_payload.items()))
    payload_hash = hashlib.sha256(payload_str.encode()).hexdigest()[:16]
    return f"event:{event_type}:{workspace_id}:{payload_hash}"