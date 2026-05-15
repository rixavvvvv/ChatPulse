import { apiClient } from "@/services/api";
import {
    CampaignDeliveryResponse,
    DashboardAlert,
    DashboardOverview,
    QueueHealthResponse,
    RecoveryAnalyticsResponse,
    RealtimeDashboardMetrics,
    RetryAnalyticsResponse,
    WebhookHealthResponse,
} from "@/types";

export interface DashboardFilters {
    start_time?: string;
    end_time?: string;
    period?: string;
    granularity?: string;
    limit?: number;
    offset?: number;
}

export const dashboardService = {
    getOverview: (filters: DashboardFilters) =>
        apiClient.get<DashboardOverview>("/dashboard/overview", { params: filters }),

    getCampaignDeliveryList: (filters: DashboardFilters) =>
        apiClient.get<CampaignDeliveryResponse>("/dashboard/campaigns/delivery", { params: filters }),

    getQueueHealth: (filters: DashboardFilters) =>
        apiClient.get<QueueHealthResponse>("/dashboard/queue/health", { params: filters }),

    getWebhookHealth: (filters: DashboardFilters) =>
        apiClient.get<WebhookHealthResponse>("/dashboard/webhooks/health", { params: filters }),

    getRetryAnalytics: (filters: DashboardFilters) =>
        apiClient.get<RetryAnalyticsResponse>("/dashboard/analytics/retry", { params: filters }),

    getRecoveryAnalytics: (filters: DashboardFilters) =>
        apiClient.get<RecoveryAnalyticsResponse>("/dashboard/analytics/recovery", { params: filters }),

    getRealtime: () => apiClient.get<RealtimeDashboardMetrics>("/dashboard/realtime"),

    getAlerts: () => apiClient.get<DashboardAlert[]>("/dashboard/alerts"),
};
