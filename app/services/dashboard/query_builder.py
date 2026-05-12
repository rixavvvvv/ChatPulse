"""
Query builder utilities for dashboard analytics.

Provides:
- Pagination helpers
- Date range resolution
- Filter compilation
- Aggregation granularity utilities
- Query optimization helpers
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import BaseModel, Field


# ─────────────────────────────────────────────────────────────────────────────
# Pagination
# ─────────────────────────────────────────────────────────────────────────────


class PaginationInput(BaseModel):
    """Pagination input parameters."""

    limit: int = Field(default=50, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)
    cursor: str | None = None


class PaginationResult(BaseModel):
    """Pagination result metadata."""

    limit: int
    offset: int
    total: int | None = None
    has_more: bool = False
    next_cursor: str | None = None
    prev_cursor: str | None = None


def build_pagination(
    limit: int = 50,
    offset: int = 0,
    total: int | None = None,
) -> PaginationResult:
    """Build pagination result from parameters."""
    has_more = total is not None and (offset + limit) < total
    return PaginationResult(
        limit=limit,
        offset=offset,
        total=total,
        has_more=has_more,
        next_cursor=str(offset + limit) if has_more else None,
        prev_cursor=str(max(0, offset - limit)) if offset > 0 else None,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Date Range
# ─────────────────────────────────────────────────────────────────────────────


class DateRangeInput(BaseModel):
    """Date range input parameters."""

    start_time: datetime | None = None
    end_time: datetime | None = None
    period: str | None = None  # today, yesterday, last_7_days, etc.


class DateRangeResult(BaseModel):
    """Resolved date range."""

    start_time: datetime
    end_time: datetime
    period: str
    days: int


# Period constants
_PERIOD_DAYS: dict[str, tuple[int, int]] = {
    "today": (0, 0),
    "yesterday": (1, 1),
    "last_7_days": (6, 0),
    "last_30_days": (29, 0),
    "last_90_days": (89, 0),
    "this_month": (0, 0),
    "last_month": (1, 1),
}


def resolve_date_range(
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    period: str | None = None,
    default_days: int = 30,
    tz: timezone = timezone.utc,
) -> DateRangeResult:
    """
    Resolve date range from various input formats.

    Priority:
    1. Explicit start/end times
    2. Period string
    3. Default range
    """
    now = datetime.now(tz)

    # If explicit times provided
    if start_time and end_time:
        start = start_time if start_time.tzinfo else start_time.replace(tzinfo=tz)
        end = end_time if end_time.tzinfo else end_time.replace(tzinfo=tz)
        days = (end - start).days
        return DateRangeResult(
            start_time=start,
            end_time=end,
            period="custom",
            days=max(1, days),
        )

    # If period string provided
    if period:
        period_lower = period.lower()
        if period_lower in _PERIOD_DAYS:
            days_back, _ = _PERIOD_DAYS[period_lower]

            if period_lower == "today":
                start = now.replace(hour=0, minute=0, second=0, microsecond=0)
                end = now
            elif period_lower == "yesterday":
                yesterday = now - timedelta(days=1)
                start = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
                end = start + timedelta(days=1)
            elif period_lower == "this_month":
                start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                end = now
            elif period_lower == "last_month":
                first_this_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                last_month_end = first_this_month
                last_month_start = (last_month_end - timedelta(days=1)).replace(day=1)
                start = last_month_start
                end = last_month_end
            else:
                start = now - timedelta(days=days_back)
                end = now

            return DateRangeResult(
                start_time=start,
                end_time=end,
                period=period_lower,
                days=max(1, days_back),
            )

    # Default: last N days
    start = now - timedelta(days=default_days)
    end = now
    return DateRangeResult(
        start_time=start,
        end_time=end,
        period=f"last_{default_days}_days",
        days=default_days,
    )


def get_comparison_range(dr: DateRangeResult) -> DateRangeResult:
    """Get the comparison period before the given date range."""
    duration = dr.end_time - dr.start_time
    comp_end = dr.start_time
    comp_start = comp_end - duration
    return DateRangeResult(
        start_time=comp_start,
        end_time=comp_end,
        period=f"comparison_{dr.period}",
        days=dr.days,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Aggregation Granularity
# ─────────────────────────────────────────────────────────────────────────────


_GRANULARITY_SECONDS: dict[str, int] = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "1h": 3600,
    "1d": 86400,
    "1w": 604800,
}


def get_bucket_interval(granularity: str, date_range: DateRangeResult) -> str:
    """
    Get appropriate bucket interval based on granularity and date range.

    Ensures reasonable number of buckets:
    - Very short ranges (< 1 day): use 1m or 5m
    - Short ranges (1-7 days): use 1h
    - Medium ranges (7-30 days): use 1d
    - Long ranges (> 30 days): use 1w
    """
    if date_range.days <= 1:
        if granularity in ("1m", "5m", "15m"):
            return granularity
        return "5m"
    elif date_range.days <= 7:
        if granularity in ("1h", "1d"):
            return granularity
        return "1h"
    elif date_range.days <= 30:
        if granularity in ("1d", "1w"):
            return granularity
        return "1d"
    else:
        return "1w"


def granularity_to_trunc_unit(granularity: str) -> str:
    """Map granularity string to PostgreSQL date_trunc unit."""
    mapping = {
        "1m": "minute",
        "5m": "minute",
        "15m": "minute",
        "1h": "hour",
        "1d": "day",
        "1w": "week",
    }
    return mapping.get(granularity, "hour")


def granularity_to_bucket_seconds(granularity: str) -> int:
    """Get bucket size in seconds."""
    return _GRANULARITY_SECONDS.get(granularity, 3600)


# ─────────────────────────────────────────────────────────────────────────────
# Filter Compilation
# ─────────────────────────────────────────────────────────────────────────────


class FilterSpec(BaseModel):
    """Filter specification for query building."""

    workspace_id: int | None = None
    campaign_ids: list[int] | None = None
    event_types: list[str] | None = None
    sources: list[str] | None = None
    tags: list[str] | None = None
    status: list[str] | None = None
    user_ids: list[int] | None = None
    contact_ids: list[int] | None = None
    queue_names: list[str] | None = None
    worker_ids: list[str] | None = None
    error_types: list[str] | None = None
    success: bool | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None


def compile_filters(
    filters: FilterSpec,
    alias: str | None = None,
) -> tuple[list[Any], dict[str, Any]]:
    """
    Compile filters into SQLAlchemy conditions and parameters.

    Returns (conditions, params) tuple.
    """
    conditions = []
    params: dict[str, Any] = {}

    if alias:
        table = f"{alias}."
    else:
        table = ""

    def add(key: str, value: Any) -> str:
        return f"__param_{key}"

    if filters.workspace_id is not None:
        conditions.append(f"{table}workspace_id = :workspace_id")
        params["workspace_id"] = filters.workspace_id

    if filters.campaign_ids:
        conditions.append(f"{table}campaign_id = ANY(:campaign_ids)")
        params["campaign_ids"] = filters.campaign_ids

    if filters.event_types:
        conditions.append(f"{table}event_type = ANY(:event_types)")
        params["event_types"] = filters.event_types

    if filters.sources:
        conditions.append(f"{table}source = ANY(:sources)")
        params["sources"] = filters.sources

    if filters.status:
        conditions.append(f"{table}status = ANY(:status)")
        params["status"] = filters.status

    if filters.user_ids:
        conditions.append(f"{table}user_id = ANY(:user_ids)")
        params["user_ids"] = filters.user_ids

    if filters.contact_ids:
        conditions.append(f"{table}contact_id = ANY(:contact_ids)")
        params["contact_ids"] = filters.contact_ids

    if filters.queue_names:
        conditions.append(f"{table}queue_name = ANY(:queue_names)")
        params["queue_names"] = filters.queue_names

    if filters.worker_ids:
        conditions.append(f"{table}worker_id = ANY(:worker_ids)")
        params["worker_ids"] = filters.worker_ids

    if filters.error_types:
        conditions.append(f"{table}error_type = ANY(:error_types)")
        params["error_types"] = filters.error_types

    if filters.success is not None:
        conditions.append(f"{table}success = :success")
        params["success"] = filters.success

    if filters.start_time:
        conditions.append(f"{table}occurred_at >= :start_time")
        params["start_time"] = filters.start_time

    if filters.end_time:
        conditions.append(f"{table}occurred_at <= :end_time")
        params["end_time"] = filters.end_time

    return conditions, params


# ─────────────────────────────────────────────────────────────────────────────
# Query Optimization Helpers
# ─────────────────────────────────────────────────────────────────────────────


def estimate_query_complexity(
    date_range: DateRangeResult,
    has_joins: bool = False,
    has_aggregates: bool = True,
) -> str:
    """
    Estimate query complexity for optimization decisions.

    Returns: "low", "medium", "high", "extreme"
    """
    score = 0

    # Date range contribution
    if date_range.days <= 1:
        score += 1
    elif date_range.days <= 7:
        score += 2
    elif date_range.days <= 30:
        score += 3
    else:
        score += 5

    # Complexity multipliers
    if has_joins:
        score += 2
    if has_aggregates:
        score += 1

    if score <= 3:
        return "low"
    elif score <= 5:
        return "medium"
    elif score <= 7:
        return "high"
    else:
        return "extreme"


def should_use_materialized_view(
    date_range: DateRangeResult,
    complexity: str,
) -> bool:
    """Determine if query should use materialized rollup tables."""
    # Use rollups for medium+ complexity or long date ranges
    return complexity in ("high", "extreme") or date_range.days > 7


def get_query_timeout(complexity: str) -> int:
    """Get appropriate query timeout in seconds based on complexity."""
    timeouts = {
        "low": 5,
        "medium": 15,
        "high": 30,
        "extreme": 60,
    }
    return timeouts.get(complexity, 15)


# ─────────────────────────────────────────────────────────────────────────────
# Sort Helpers
# ─────────────────────────────────────────────────────────────────────────────

SORTABLE_FIELDS = {
    "occurred_at",
    "created_at",
    "timestamp",
    "workspace_id",
    "campaign_id",
    "event_type",
    "total_count",
    "success_count",
    "failure_count",
    "duration_avg",
    "delivery_rate",
}


def validate_sort_field(field: str) -> str:
    """Validate and normalize sort field."""
    return field if field in SORTABLE_FIELDS else "occurred_at"


def validate_sort_direction(direction: str) -> str:
    """Validate and normalize sort direction."""
    d = direction.lower()
    return "desc" if d not in ("asc", "desc") else d
