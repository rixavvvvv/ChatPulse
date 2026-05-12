"""
Dashboard analytics services.

Provides:
- Query builder utilities
- Redis caching layer
- Dashboard query service
- Real-time pub/sub service
"""

from app.services.dashboard.cache import DashboardCacheService, get_dashboard_cache
from app.services.dashboard.query_builder import (
    DateRangeInput,
    DateRangeResult,
    FilterSpec,
    PaginationInput,
    PaginationResult,
    build_pagination,
    compile_filters,
    get_bucket_interval,
    get_comparison_range,
    resolve_date_range,
)
from app.services.dashboard.query_service import DashboardQueryService
from app.services.dashboard.realtime import (
    Channel,
    EventKind,
    RealtimeMessage,
    RealtimePubSubService,
    get_realtime_service,
)

__all__ = [
    # Cache
    "DashboardCacheService",
    "get_dashboard_cache",
    # Query builder
    "PaginationInput",
    "PaginationResult",
    "DateRangeInput",
    "DateRangeResult",
    "FilterSpec",
    "build_pagination",
    "compile_filters",
    "resolve_date_range",
    "get_comparison_range",
    "get_bucket_interval",
    # Query service
    "DashboardQueryService",
    # Realtime
    "RealtimePubSubService",
    "RealtimeMessage",
    "Channel",
    "EventKind",
    "get_realtime_service",
]
