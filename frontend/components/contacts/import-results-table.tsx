"use client";

import React from "react";
import { AlertTriangle } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/states";

interface ImportRowError {
    row_number: number;
    error: string;
    raw: Record<string, string>;
}

interface ImportResultsTableProps {
    jobId: number;
    errors: ImportRowError[];
    isLoading?: boolean;
}

export function ImportResultsTable({ jobId, errors, isLoading }: ImportResultsTableProps) {
    if (isLoading) {
        return (
            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2 text-lg">
                        <AlertTriangle className="h-5 w-5 text-amber-500" />
                        Failed Rows
                    </CardTitle>
                </CardHeader>
                <CardContent>
                    <div className="space-y-3">
                        {[1, 2, 3, 4, 5].map((i) => (
                            <div key={i} className="animate-pulse flex gap-4">
                                <div className="h-8 w-16 rounded bg-muted" />
                                <div className="h-8 flex-1 rounded bg-muted" />
                            </div>
                        ))}
                    </div>
                </CardContent>
            </Card>
        );
    }

    if (errors.length === 0) {
        return (
            <Card>
                <CardContent className="pt-6">
                    <EmptyState
                        title="No failed rows"
                        description="All rows were processed successfully"
                        icon={AlertTriangle}
                    />
                </CardContent>
            </Card>
        );
    }

    return (
        <Card>
            <CardHeader>
                <CardTitle className="flex items-center gap-2 text-lg">
                    <AlertTriangle className="h-5 w-5 text-amber-500" />
                    Failed Rows ({errors.length})
                </CardTitle>
            </CardHeader>
            <CardContent>
                <div className="max-h-80 overflow-auto rounded-lg border">
                    <table className="w-full text-sm">
                        <thead className="bg-muted sticky top-0">
                            <tr>
                                <th className="px-4 py-3 text-left font-medium">Row</th>
                                <th className="px-4 py-3 text-left font-medium">Error</th>
                                <th className="px-4 py-3 text-left font-medium">Data</th>
                            </tr>
                        </thead>
                        <tbody>
                            {errors.map((error) => (
                                <tr key={error.row_number} className="border-t hover:bg-muted/30">
                                    <td className="px-4 py-3">
                                        <Badge variant="outline">#{error.row_number}</Badge>
                                    </td>
                                    <td className="px-4 py-3">
                                        <p className="text-red-600">{error.error}</p>
                                    </td>
                                    <td className="px-4 py-3">
                                        <div className="flex flex-wrap gap-1">
                                            {Object.entries(error.raw).map(([key, value]) => (
                                                <span
                                                    key={key}
                                                    className="rounded bg-muted px-2 py-0.5 text-xs"
                                                >
                                                    {key}: {value || "(empty)"}
                                                </span>
                                            ))}
                                        </div>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </CardContent>
        </Card>
    );
}