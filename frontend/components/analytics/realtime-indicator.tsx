import React from "react";
import { cn } from "@/lib/utils";

interface RealtimeIndicatorProps {
    status: "connecting" | "connected" | "reconnecting" | "disconnected";
    lastEventAt?: string | null;
}

export function RealtimeIndicator({ status, lastEventAt }: RealtimeIndicatorProps) {
    const color =
        status === "connected"
            ? "bg-emerald-500"
            : status === "reconnecting"
            ? "bg-yellow-500"
            : status === "connecting"
            ? "bg-blue-500"
            : "bg-red-500";

    return (
        <div className="flex items-center gap-2 text-xs text-gray-500">
            <span className={cn("h-2 w-2 rounded-full", color)} />
            <span className="capitalize">{status}</span>
            {lastEventAt && <span>· Last update {new Date(lastEventAt).toLocaleTimeString()}</span>}
        </div>
    );
}
