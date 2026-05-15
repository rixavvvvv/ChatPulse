import { create } from "zustand";
import { DashboardAlert, RealtimeDashboardMetrics } from "@/types";

interface AnalyticsDashboardState {
    realtime?: RealtimeDashboardMetrics | null;
    alerts: DashboardAlert[];
    sseStatus: "connecting" | "connected" | "reconnecting" | "disconnected";
    lastEventAt?: string | null;
    setRealtime: (data?: RealtimeDashboardMetrics | null) => void;
    setAlerts: (alerts: DashboardAlert[]) => void;
    setSseStatus: (status: AnalyticsDashboardState["sseStatus"]) => void;
    setLastEventAt: (timestamp?: string | null) => void;
}

export const useAnalyticsDashboardStore = create<AnalyticsDashboardState>((set) => ({
    realtime: null,
    alerts: [],
    sseStatus: "disconnected",
    lastEventAt: null,
    setRealtime: (data) => set({ realtime: data ?? null }),
    setAlerts: (alerts) => set({ alerts }),
    setSseStatus: (status) => set({ sseStatus: status }),
    setLastEventAt: (timestamp) => set({ lastEventAt: timestamp ?? null }),
}));
