import React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface StatCardProps {
    label: string;
    value: string | number;
    sublabel?: string;
    trend?: string;
}

export function StatCard({ label, value, sublabel, trend }: StatCardProps) {
    return (
        <Card>
            <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium text-gray-600 dark:text-gray-400">
                    {label}
                </CardTitle>
            </CardHeader>
            <CardContent>
                <div className="text-2xl font-semibold">{value}</div>
                {sublabel && <div className="text-xs text-gray-500 mt-1">{sublabel}</div>}
                {trend && <div className="text-xs text-emerald-600 mt-1">{trend}</div>}
            </CardContent>
        </Card>
    );
}
