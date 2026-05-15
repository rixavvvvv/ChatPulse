"use client";

import { cn } from "@/lib/utils";

interface ContactsTableSkeletonProps {
    rows?: number;
    className?: string;
}

export function ContactsTableSkeleton({
    rows = 10,
    className,
}: ContactsTableSkeletonProps) {
    return (
        <div className={cn("space-y-4", className)}>
            <div className="flex items-center gap-4">
                <div className="h-10 w-64 animate-pulse rounded-md bg-muted" />
                <div className="h-10 w-24 animate-pulse rounded-md bg-muted" />
            </div>

            <div className="rounded-lg border border-border overflow-hidden">
                <table className="w-full">
                    <thead className="bg-muted/50 border-b">
                        <tr>
                            {[40, 200, 150, 200, 180, 100, 150, 120, 50].map((width, i) => (
                                <th
                                    key={i}
                                    className="px-4 py-3 text-left text-sm font-medium text-muted-foreground"
                                    style={{ width: `${width}px` }}
                                >
                                    <div className="h-4 w-20 animate-pulse rounded bg-muted-foreground/20" />
                                </th>
                            ))}
                        </tr>
                    </thead>
                    <tbody>
                        {Array.from({ length: rows }).map((_, i) => (
                            <tr key={i} className="border-b">
                                {[40, 200, 150, 200, 180, 100, 150, 120, 50].map((width, j) => (
                                    <td key={j} className="px-4 py-3">
                                        <div
                                            className="h-4 animate-pulse rounded bg-muted-foreground/20"
                                            style={{ width: `${Math.random() * 40 + 20}px` }}
                                        />
                                    </td>
                                ))}
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>

            <div className="flex items-center justify-between">
                <div className="h-4 w-48 animate-pulse rounded bg-muted-foreground/20" />
                <div className="flex items-center gap-1">
                    {Array.from({ length: 5 }).map((_, i) => (
                        <div
                            key={i}
                            className="h-8 w-8 animate-pulse rounded border bg-muted-foreground/20"
                        />
                    ))}
                </div>
            </div>
        </div>
    );
}