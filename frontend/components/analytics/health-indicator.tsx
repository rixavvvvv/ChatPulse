import React from "react";
import { cn } from "@/lib/utils";

interface HealthIndicatorProps {
    label: string;
    value: number;
    threshold?: number;
    direction?: "higher" | "lower";
}

export function HealthIndicator({ label, value, threshold = 90, direction = "higher" }: HealthIndicatorProps) {
    const successValue = direction === "higher" ? value : 100 - value;
    const status = successValue >= threshold ? "good" : successValue >= threshold * 0.7 ? "warn" : "bad";

    return (
        <div className="flex items-center justify-between text-sm">
            <span className="text-gray-600 dark:text-gray-400">{label}</span>
            <span
                className={cn(
                    "px-2 py-1 rounded-full text-xs",
                    status === "good" && "bg-emerald-100 text-emerald-700",
                    status === "warn" && "bg-yellow-100 text-yellow-700",
                    status === "bad" && "bg-red-100 text-red-700"
                )}
            >
                {value.toFixed(1)}%
            </span>
        </div>
    );
}
