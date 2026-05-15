import { useQuery } from "@tanstack/react-query";
import { dashboardService, DashboardFilters } from "@/services/analytics/dashboard-service";

export function useDashboardOverview(filters: DashboardFilters) {
    return useQuery({
        queryKey: ["dashboard", "overview", filters],
        queryFn: () => dashboardService.getOverview(filters),
    });
}

export function useCampaignDelivery(filters: DashboardFilters) {
    return useQuery({
        queryKey: ["dashboard", "campaigns", filters],
        queryFn: () => dashboardService.getCampaignDeliveryList(filters),
    });
}

export function useQueueHealth(filters: DashboardFilters) {
    return useQuery({
        queryKey: ["dashboard", "queue", filters],
        queryFn: () => dashboardService.getQueueHealth(filters),
    });
}

export function useWebhookHealth(filters: DashboardFilters) {
    return useQuery({
        queryKey: ["dashboard", "webhooks", filters],
        queryFn: () => dashboardService.getWebhookHealth(filters),
    });
}

export function useRetryAnalytics(filters: DashboardFilters) {
    return useQuery({
        queryKey: ["dashboard", "retry", filters],
        queryFn: () => dashboardService.getRetryAnalytics(filters),
    });
}

export function useRecoveryAnalytics(filters: DashboardFilters) {
    return useQuery({
        queryKey: ["dashboard", "recovery", filters],
        queryFn: () => dashboardService.getRecoveryAnalytics(filters),
    });
}

export function useRealtimeMetrics() {
    return useQuery({
        queryKey: ["dashboard", "realtime"],
        queryFn: () => dashboardService.getRealtime(),
        refetchInterval: 10000,
    });
}

export function useDashboardAlerts() {
    return useQuery({
        queryKey: ["dashboard", "alerts"],
        queryFn: () => dashboardService.getAlerts(),
        refetchInterval: 30000,
    });
}
