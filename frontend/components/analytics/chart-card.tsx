import React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface ChartCardProps {
    title: string;
    description?: string;
    children: React.ReactNode;
    contentClassName?: string;
}

export function ChartCard({ title, description, children, contentClassName }: ChartCardProps) {
    return (
        <Card>
            <CardHeader>
                <CardTitle>{title}</CardTitle>
                {description && <p className="text-xs text-gray-500">{description}</p>}
            </CardHeader>
            <CardContent>
                <div className={contentClassName ?? "h-64 w-full"}>{children}</div>
            </CardContent>
        </Card>
    );
}
