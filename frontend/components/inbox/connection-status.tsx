import React from "react";
import { cn } from "@/lib/utils";

interface ConnectionStatusProps {
    status: "connected" | "connecting" | "reconnecting" | "disconnected";
}

const statusColors: Record<ConnectionStatusProps["status"], string> = {
    connected: "text-emerald-600",
    connecting: "text-yellow-600",
    reconnecting: "text-orange-600",
    disconnected: "text-red-600",
};

export function ConnectionStatus({ status }: ConnectionStatusProps) {
    return (
        <div className="flex items-center gap-2 text-xs">
            <span className={cn("h-2 w-2 rounded-full", statusColors[status])} />
            <span className="text-gray-500 dark:text-gray-400 capitalize">{status}</span>
        </div>
    );
}
