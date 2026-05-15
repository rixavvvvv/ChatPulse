"use client";

import React from "react";
import { RefreshCw, CheckCircle, XCircle, Clock, AlertTriangle, Loader2, Users } from "lucide-react";
import { formatDistanceToNow, format } from "date-fns";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";

interface SegmentStatusIndicatorProps {
    status: "idle" | "materializing" | "ready" | "error";
    showLabel?: boolean;
    className?: string;
}

export function SegmentStatusIndicator({
    status,
    showLabel = true,
    className,
}: SegmentStatusIndicatorProps) {
    const statusConfig = {
        idle: {
            icon: Clock,
            label: "Not Materialized",
            variant: "outline" as const,
            color: "text-gray-500",
        },
        materializing: {
            icon: Loader2,
            label: "Materializing...",
            variant: "default" as const,
            color: "text-blue-500",
        },
        ready: {
            icon: CheckCircle,
            label: "Ready",
            variant: "secondary" as const,
            color: "text-green-500",
        },
        error: {
            icon: XCircle,
            label: "Error",
            variant: "destructive" as const,
            color: "text-red-500",
        },
    };

    const config = statusConfig[status];
    const Icon = config.icon;

    return (
        <div className={cn("flex items-center gap-2", className)}>
            <Icon
                className={cn(
                    "h-4 w-4",
                    status === "materializing" && "animate-spin",
                    config.color
                )}
            />
            {showLabel && <Badge variant={config.variant}>{config.label}</Badge>}
        </div>
    );
}

interface RefreshControlsProps {
    isRefreshing: boolean;
    lastRefreshed: string | null;
    onRefresh: () => void;
    disabled?: boolean;
    size?: "sm" | "default";
}

export function RefreshControls({
    isRefreshing,
    lastRefreshed,
    onRefresh,
    disabled = false,
    size = "default",
}: RefreshControlsProps) {
    return (
        <div className="flex items-center gap-2">
            <Button
                size={size}
                variant="outline"
                onClick={onRefresh}
                disabled={disabled || isRefreshing}
            >
                {isRefreshing ? (
                    <RefreshCw className={cn("h-4 w-4", size === "sm" && "h-3 w-3") + " animate-spin"} />
                ) : (
                    <RefreshCw className={cn("h-4 w-4", size === "sm" && "h-3 w-3")} />
                )}
                {size !== "sm" && (isRefreshing ? "Refreshing..." : "Refresh")}
            </Button>
            {lastRefreshed && (
                <span className="text-xs text-muted-foreground">
                    Last: {formatDistanceToNow(new Date(lastRefreshed), { addSuffix: true })}
                </span>
            )}
        </div>
    );
}

interface SegmentMetricsCardProps {
    segmentName: string;
    size: number;
    lastMaterialized: string | null;
    status: "idle" | "materializing" | "ready" | "error";
    errorMessage?: string | null;
    onRefresh?: () => void;
    isRefreshing?: boolean;
}

export function SegmentMetricsCard({
    segmentName,
    size,
    lastMaterialized,
    status,
    errorMessage,
    onRefresh,
    isRefreshing = false,
}: SegmentMetricsCardProps) {
    return (
        <div className="rounded-lg border bg-card p-4 space-y-4">
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                    <Users className="h-5 w-5 text-muted-foreground" />
                    <span className="font-medium">{segmentName}</span>
                </div>
                <SegmentStatusIndicator status={status} />
            </div>

            <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                    <p className="text-muted-foreground">Segment Size</p>
                    <p className="text-lg font-semibold">{size.toLocaleString()}</p>
                </div>
                <div>
                    <p className="text-muted-foreground">Last Materialized</p>
                    <p className="font-medium">
                        {lastMaterialized
                            ? formatDistanceToNow(new Date(lastMaterialized), { addSuffix: true })
                            : "Never"}
                    </p>
                </div>
            </div>

            {status === "materializing" && (
                <div className="space-y-1">
                    <p className="text-xs text-muted-foreground">Materializing contacts...</p>
                    <Progress value={undefined} className="h-1 animate-pulse" />
                </div>
            )}

            {status === "error" && errorMessage && (
                <div className="rounded-md bg-red-50 p-3 text-sm">
                    <div className="flex items-start gap-2">
                        <AlertTriangle className="h-4 w-4 text-red-500 mt-0.5" />
                        <p className="text-red-700">{errorMessage}</p>
                    </div>
                </div>
            )}

            {onRefresh && status !== "materializing" && (
                <div className="flex justify-end">
                    <RefreshControls
                        isRefreshing={isRefreshing}
                        lastRefreshed={lastMaterialized}
                        onRefresh={onRefresh}
                        size="sm"
                    />
                </div>
            )}
        </div>
    );
}

interface SegmentMaterializationPanelProps {
    segments: {
        id: number;
        name: string;
        approx_size: number;
        last_materialized_at: string | null;
        status: string;
        materializing?: boolean;
        error_message?: string | null;
    }[];
    isLoading?: boolean;
    onMaterialize: (segmentId: number) => void;
    isMaterializing?: (segmentId: number) => boolean;
    onRefreshAll?: () => void;
    isRefreshingAll?: boolean;
}

export function SegmentMaterializationPanel({
    segments,
    isLoading,
    onMaterialize,
    isMaterializing,
    onRefreshAll,
    isRefreshingAll = false,
}: SegmentMaterializationPanelProps) {
    if (isLoading) {
        return (
            <div className="space-y-4">
                {[1, 2, 3].map((i) => (
                    <div key={i} className="animate-pulse rounded-lg border p-4">
                        <div className="flex items-center justify-between">
                            <div className="h-5 w-32 rounded bg-muted" />
                            <div className="h-6 w-20 rounded bg-muted" />
                        </div>
                        <div className="mt-4 grid grid-cols-2 gap-4">
                            <div className="h-8 w-20 rounded bg-muted" />
                            <div className="h-8 w-32 rounded bg-muted" />
                        </div>
                    </div>
                ))}
            </div>
        );
    }

    if (segments.length === 0) {
        return (
            <div className="text-center py-8 text-muted-foreground">
                <Users className="h-8 w-8 mx-auto mb-2 opacity-50" />
                <p>No segments to display</p>
            </div>
        );
    }

    const getSegmentStatus = (segment: typeof segments[0]): "idle" | "materializing" | "ready" | "error" => {
        if (segment.materializing || isMaterializing?.(segment.id)) {
            return "materializing";
        }
        if (segment.status === "active" || segment.approx_size > 0) {
            return "ready";
        }
        if (segment.status === "failed" || segment.error_message) {
            return "error";
        }
        return "idle";
    };

    const hasMaterializedSegments = segments.some(
        (s) => s.status === "active" || s.approx_size > 0
    );

    return (
        <div className="space-y-4">
            {onRefreshAll && (
                <div className="flex items-center justify-between">
                    <div className="text-sm text-muted-foreground">
                        {segments.filter((s) => getSegmentStatus(s) === "ready").length} of {segments.length} materialized
                    </div>
                    <Button
                        variant="outline"
                        size="sm"
                        onClick={onRefreshAll}
                        disabled={isRefreshingAll}
                    >
                        {isRefreshingAll ? (
                            <RefreshCw className="h-4 w-4 animate-spin" />
                        ) : (
                            <RefreshCw className="h-4 w-4" />
                        )}
                        <span className="ml-2">Refresh All</span>
                    </Button>
                </div>
            )}

            <div className="space-y-3">
                {segments.map((segment) => {
                    const status = getSegmentStatus(segment);
                    const isCurrentlyMaterializing = segment.materializing || isMaterializing?.(segment.id);

                    return (
                        <div
                            key={segment.id}
                            className={cn(
                                "rounded-lg border bg-card p-4 transition-colors",
                                status === "materializing" && "border-blue-200 bg-blue-50/50"
                            )}
                        >
                            <div className="flex items-center justify-between mb-3">
                                <div className="flex items-center gap-2">
                                    <Users className="h-4 w-4 text-muted-foreground" />
                                    <span className="font-medium">{segment.name}</span>
                                </div>
                                <SegmentStatusIndicator status={status} />
                            </div>

                            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm mb-3">
                                <div>
                                    <p className="text-muted-foreground">Size</p>
                                    <p className="font-semibold text-lg">{segment.approx_size.toLocaleString()}</p>
                                </div>
                                <div>
                                    <p className="text-muted-foreground">Last Materialized</p>
                                    <p className="font-medium">
                                        {segment.last_materialized_at
                                            ? formatDistanceToNow(new Date(segment.last_materialized_at), { addSuffix: true })
                                            : "Never"}
                                    </p>
                                </div>
                                <div>
                                    <p className="text-muted-foreground">Status</p>
                                    <Badge
                                        variant={
                                            status === "ready"
                                                ? "secondary"
                                                : status === "error"
                                                ? "destructive"
                                                : status === "materializing"
                                                ? "default"
                                                : "outline"
                                        }
                                    >
                                        {status === "ready" ? "Active" : segment.status}
                                    </Badge>
                                </div>
                                <div>
                                    <p className="text-muted-foreground">Next Action</p>
                                    {status === "materializing" ? (
                                        <div className="flex items-center gap-1 text-blue-600">
                                            <Loader2 className="h-3 w-3 animate-spin" />
                                            <span className="text-xs">Processing</span>
                                        </div>
                                    ) : status === "idle" ? (
                                        <Button
                                            size="sm"
                                            variant="ghost"
                                            className="h-6 text-xs"
                                            onClick={() => onMaterialize(segment.id)}
                                        >
                                            Materialize
                                        </Button>
                                    ) : (
                                        <Button
                                            size="sm"
                                            variant="ghost"
                                            className="h-6 text-xs"
                                            onClick={() => onMaterialize(segment.id)}
                                        >
                                            <RefreshCw className="h-3 w-3 mr-1" />
                                            Refresh
                                        </Button>
                                    )}
                                </div>
                            </div>

                            {status === "materializing" && (
                                <div className="space-y-1">
                                    <Progress value={undefined} className="h-1.5 animate-pulse" />
                                    <p className="text-xs text-muted-foreground text-center">
                                        Computing segment membership...
                                    </p>
                                </div>
                            )}

                            {status === "error" && segment.error_message && (
                                <div className="mt-3 rounded-md bg-red-50 p-2 text-sm">
                                    <div className="flex items-start gap-2">
                                        <AlertTriangle className="h-4 w-4 text-red-500 mt-0.5 flex-shrink-0" />
                                        <p className="text-red-700 text-xs">{segment.error_message}</p>
                                    </div>
                                </div>
                            )}

                            {segment.last_materialized_at && (
                                <p className="text-xs text-muted-foreground mt-2">
                                    Last updated: {format(new Date(segment.last_materialized_at), "PPpp")}
                                </p>
                            )}
                        </div>
                    );
                })}
            </div>
        </div>
    );
}