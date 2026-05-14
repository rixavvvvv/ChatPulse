import React from "react";
import { cn } from "@/lib/utils";

interface AgentAvatarProps {
    name: string;
    size?: "sm" | "md" | "lg";
    status?: "online" | "away" | "busy" | "offline";
}

const sizes = {
    sm: "h-7 w-7 text-xs",
    md: "h-9 w-9 text-sm",
    lg: "h-12 w-12 text-base",
};

const statusColors = {
    online: "bg-emerald-500",
    away: "bg-yellow-500",
    busy: "bg-red-500",
    offline: "bg-gray-400",
};

export function AgentAvatar({ name, size = "md", status = "offline" }: AgentAvatarProps) {
    const initials = name
        .split(" ")
        .map((part) => part[0])
        .slice(0, 2)
        .join("")
        .toUpperCase();

    return (
        <div className="relative">
            <div
                className={cn(
                    "rounded-full bg-blue-600 text-white flex items-center justify-center font-semibold",
                    sizes[size]
                )}
            >
                {initials}
            </div>
            <span
                className={cn(
                    "absolute -bottom-0.5 -right-0.5 h-3 w-3 rounded-full border-2 border-white dark:border-gray-950",
                    statusColors[status]
                )}
            />
        </div>
    );
}
