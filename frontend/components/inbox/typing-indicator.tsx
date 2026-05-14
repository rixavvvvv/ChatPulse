import React from "react";
import { cn } from "@/lib/utils";

interface TypingIndicatorProps {
    isActive: boolean;
    label?: string;
}

export function TypingIndicator({ isActive, label = "Typing" }: TypingIndicatorProps) {
    if (!isActive) return null;

    return (
        <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
            <span>{label}</span>
            <div className="flex gap-1">
                <span className={cn("h-2 w-2 rounded-full bg-gray-400 animate-bounce", "[animation-delay:-0.3s]")} />
                <span className={cn("h-2 w-2 rounded-full bg-gray-400 animate-bounce", "[animation-delay:-0.15s]")} />
                <span className={cn("h-2 w-2 rounded-full bg-gray-400 animate-bounce")} />
            </div>
        </div>
    );
}
