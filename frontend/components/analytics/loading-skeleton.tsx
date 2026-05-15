import React from "react";
import { cn } from "@/lib/utils";

export function LoadingSkeleton({ className }: { className?: string }) {
    return (
        <div className={cn("animate-pulse rounded-lg bg-gray-200 dark:bg-gray-800", className)} />
    );
}
