"use client";

import React from "react";
import { CheckCircle, XCircle, Loader2, Clock, AlertTriangle, SkipForward } from "lucide-react";
import { formatDistanceToNow } from "date-fns";

import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";

interface ImportProgressTrackerProps {
    jobId: number;
    status: "queued" | "processing" | "completed" | "failed";
    totalRows: number;
    processedRows: number;
    insertedRows: number;
    skippedRows: number;
    failedRows: number;
    errorMessage?: string | null;
    createdAt: string;
    completedAt?: string | null;
    onViewErrors?: () => void;
}

export function ImportProgressTracker({
    status,
    totalRows,
    processedRows,
    insertedRows,
    skippedRows,
    failedRows,
    errorMessage,
    createdAt,
    completedAt,
    onViewErrors,
}: ImportProgressTrackerProps) {
    const progress = totalRows > 0 ? (processedRows / totalRows) * 100 : 0;

    const StatusIcon = {
        queued: Clock,
        processing: Loader2,
        completed: CheckCircle,
        failed: XCircle,
    }[status];

    const statusColors = {
        queued: "bg-slate-500",
        processing: "bg-blue-500 animate-pulse",
        completed: "bg-green-500",
        failed: "bg-red-500",
    }[status];

    return (
        <Card>
            <CardContent className="pt-4">
                <div className="flex items-start justify-between">
                    <div className="flex items-center gap-3">
                        <div className={`rounded-full p-2 ${statusColors} text-white`}>
                            <StatusIcon className={`h-4 w-4 ${status === "processing" ? "animate-spin" : ""}`} />
                        </div>
                        <div>
                            <div className="flex items-center gap-2">
                                <Badge
                                    variant={
                                        status === "completed"
                                            ? "secondary"
                                            : status === "failed"
                                            ? "destructive"
                                            : status === "processing"
                                            ? "default"
                                            : "outline"
                                    }
                                >
                                    {status}
                                </Badge>
                                <span className="text-sm text-muted-foreground">
                                    {formatDistanceToNow(new Date(createdAt), { addSuffix: true })}
                                </span>
                            </div>
                            {errorMessage && (
                                <p className="mt-1 text-sm text-red-500">{errorMessage}</p>
                            )}
                        </div>
                    </div>
                    {failedRows > 0 && onViewErrors && (
                        <button
                            onClick={onViewErrors}
                            className="text-sm text-primary hover:underline"
                        >
                            View {failedRows} failed
                        </button>
                    )}
                </div>

                <div className="mt-4 space-y-2">
                    <div className="flex justify-between text-sm">
                        <span className="text-muted-foreground">
                            {processedRows} of {totalRows} rows processed
                        </span>
                        <span className="font-medium">{Math.round(progress)}%</span>
                    </div>
                    <Progress value={progress} className="h-2" />
                </div>

                <div className="mt-4 grid grid-cols-3 gap-4 text-center">
                    <div className="rounded-lg bg-green-50 p-3">
                        <p className="text-2xl font-bold text-green-600">{insertedRows}</p>
                        <p className="text-xs text-green-700">Added</p>
                    </div>
                    <div className="rounded-lg bg-amber-50 p-3">
                        <p className="text-2xl font-bold text-amber-600">{skippedRows}</p>
                        <p className="text-xs text-amber-700">Skipped</p>
                    </div>
                    <div className="rounded-lg bg-red-50 p-3">
                        <p className="text-2xl font-bold text-red-600">{failedRows}</p>
                        <p className="text-xs text-red-700">Failed</p>
                    </div>
                </div>

                {completedAt && (
                    <p className="mt-3 text-center text-xs text-muted-foreground">
                        Completed {formatDistanceToNow(new Date(completedAt), { addSuffix: true })}
                    </p>
                )}
            </CardContent>
        </Card>
    );
}

export function ImportJobsListSkeleton() {
    return (
        <div className="space-y-3">
            {[1, 2, 3].map((i) => (
                <div key={i} className="animate-pulse rounded-lg border p-4">
                    <div className="flex items-center gap-3">
                        <div className="h-10 w-10 rounded-full bg-muted" />
                        <div className="flex-1 space-y-2">
                            <div className="h-4 w-24 rounded bg-muted" />
                            <div className="h-3 w-32 rounded bg-muted" />
                        </div>
                    </div>
                    <div className="mt-4 h-2 rounded bg-muted" />
                </div>
            ))}
        </div>
    );
}