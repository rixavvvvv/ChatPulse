"use client";

import { useEffect, useMemo, useState } from "react";
import { CheckCheck, MessageSquareText, TriangleAlert } from "lucide-react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { apiRequest } from "@/lib/api";
import { getSession } from "@/lib/session";

type AnalyticsPayload = {
    workspace_id: number;
    total_sent: number;
    delivered_percentage: number;
    read_percentage: number;
    failure_percentage: number;
};

type TimelinePoint = {
    date: string;
    sent: number;
    delivered: number;
};

type TimelinePayload = {
    workspace_id: number;
    points: TimelinePoint[];
};

export default function DashboardPage() {
    const [analytics, setAnalytics] = useState<AnalyticsPayload | null>(null);
    const [timeline, setTimeline] = useState<TimelinePoint[]>([]);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        const load = async () => {
            const session = getSession();
            if (!session) {
                return;
            }

            try {
                const [analyticsPayload, timelinePayload] = await Promise.all([
                    apiRequest<AnalyticsPayload>("/analytics/messages", {}, session.access_token),
                    apiRequest<TimelinePayload>("/analytics/messages/timeline?days=14", {}, session.access_token),
                ]);
                setAnalytics(analyticsPayload);
                setTimeline(timelinePayload.points);
            } catch (err) {
                setError(err instanceof Error ? err.message : "Failed to load analytics");
            }
        };

        void load();
    }, []);

    const maxCount = useMemo(() => {
        if (timeline.length === 0) {
            return 1;
        }
        return Math.max(1, ...timeline.flatMap((point) => [point.sent, point.delivered]));
    }, [timeline]);

    const metrics = [
        {
            label: "Messages Sent",
            value: analytics?.total_sent ?? 0,
            detail: "Current cycle",
            icon: MessageSquareText,
        },
        {
            label: "Delivered %",
            value: `${analytics?.delivered_percentage ?? 0}%`,
            detail: "Delivered and read",
            icon: CheckCheck,
        },
        {
            label: "Failure %",
            value: `${analytics?.failure_percentage ?? 0}%`,
            detail: "Failed delivery events",
            icon: TriangleAlert,
        },
    ];

    return (
        <div className="space-y-6">
            <section className="rounded-3xl border border-sky-100 bg-gradient-to-r from-sky-100/80 via-cyan-50 to-orange-50 p-8 shadow-soft">
                <p className="mb-2 text-xs font-semibold uppercase tracking-[0.22em] text-sky-700">Overview</p>
                <h2 className="font-[var(--font-space-grotesk)] text-3xl font-semibold text-slate-900 md:text-4xl">
                    Message performance at a glance
                </h2>
                <p className="mt-3 max-w-2xl text-slate-700">
                    Track campaign health, monitor replies, and keep outreach quality high with concise personalized templates.
                </p>
            </section>

            <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
                {metrics.map((item) => (
                    <Card key={item.label}>
                        <CardHeader className="flex flex-row items-center justify-between space-y-0">
                            <CardDescription>{item.label}</CardDescription>
                            <item.icon className="h-4 w-4 text-sky-700" />
                        </CardHeader>
                        <CardContent>
                            <CardTitle className="text-3xl">{item.value}</CardTitle>
                            <p className="mt-2 text-sm text-slate-600">{item.detail}</p>
                        </CardContent>
                    </Card>
                ))}
            </section>

            <Card>
                <CardHeader>
                    <CardTitle>Sent vs Delivered (14 days)</CardTitle>
                    <CardDescription>Live analytics feed from message events.</CardDescription>
                </CardHeader>
                <CardContent>
                    <div className="grid grid-cols-[repeat(14,minmax(0,1fr))] gap-2">
                        {timeline.map((point) => {
                            const sentHeight = Math.max(4, Math.round((point.sent / maxCount) * 120));
                            const deliveredHeight = Math.max(4, Math.round((point.delivered / maxCount) * 120));

                            return (
                                <div key={point.date} className="flex flex-col items-center gap-2">
                                    <div className="flex h-32 items-end gap-1">
                                        <div className="w-2 rounded-sm bg-sky-400" style={{ height: `${sentHeight}px` }} />
                                        <div className="w-2 rounded-sm bg-emerald-400" style={{ height: `${deliveredHeight}px` }} />
                                    </div>
                                    <p className="text-[10px] text-slate-500">{point.date.slice(5)}</p>
                                </div>
                            );
                        })}
                    </div>
                    <div className="mt-4 flex items-center gap-4 text-xs text-slate-600">
                        <span className="inline-flex items-center gap-1"><span className="h-2 w-2 rounded-sm bg-sky-400" /> Sent</span>
                        <span className="inline-flex items-center gap-1"><span className="h-2 w-2 rounded-sm bg-emerald-400" /> Delivered</span>
                    </div>
                </CardContent>
            </Card>

            {error ? <p className="text-sm text-rose-700">{error}</p> : null}
        </div>
    );
}
