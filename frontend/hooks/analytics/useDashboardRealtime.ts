import { useEffect } from "react";
import { useAnalyticsDashboardStore } from "@/stores/analytics-dashboard";
import { RealtimeDashboardMetrics, DashboardAlert } from "@/types";

interface RealtimeEventPayload {
    kind: string;
    data: Record<string, unknown>;
    timestamp?: string;
}

export function useDashboardRealtime() {
    const { setRealtime, setAlerts, setSseStatus, setLastEventAt } = useAnalyticsDashboardStore();

    useEffect(() => {
        const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
        const baseUrl = process.env.NEXT_PUBLIC_API_URL?.replace("/api", "") || "http://localhost:8000";
        const url = token
            ? `${baseUrl}/dashboard/realtime/stream?token=${encodeURIComponent(token)}`
            : `${baseUrl}/dashboard/realtime/stream`;

        setSseStatus("connecting");

        const eventSource = new EventSource(url, { withCredentials: true });

        const handleMessage = (event: MessageEvent) => {
            if (!event.data) return;
            try {
                const payload = JSON.parse(event.data) as RealtimeEventPayload;
                setLastEventAt(new Date().toISOString());

                if (payload.kind === "metric.update") {
                    setRealtime(payload.data as RealtimeDashboardMetrics);
                }
                if (payload.kind === "alert") {
                    setAlerts([payload.data as DashboardAlert]);
                }
            } catch {
                // Ignore malformed events
            }
        };

        eventSource.onopen = () => setSseStatus("connected");
        eventSource.onerror = () => setSseStatus("reconnecting");

        eventSource.addEventListener("metric.update", handleMessage);
        eventSource.addEventListener("alert", handleMessage);
        eventSource.addEventListener("heartbeat", () => {
            setLastEventAt(new Date().toISOString());
        });

        return () => {
            eventSource.close();
            setSseStatus("disconnected");
        };
    }, [setRealtime, setAlerts, setSseStatus, setLastEventAt]);
}
