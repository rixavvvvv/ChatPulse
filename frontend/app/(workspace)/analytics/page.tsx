"use client";

import React, { useMemo, useState } from "react";
import {
    LineChart,
    Line,
    XAxis,
    YAxis,
    Tooltip,
    ResponsiveContainer,
    BarChart,
    Bar,
    Legend,
} from "recharts";
import { PageLayout } from "@/components/layout/page-layout";
import { StatCard } from "@/components/analytics/stat-card";
import { ChartCard } from "@/components/analytics/chart-card";
import { MetricsTable } from "@/components/analytics/metrics-table";
import { HealthIndicator } from "@/components/analytics/health-indicator";
import { RealtimeIndicator } from "@/components/analytics/realtime-indicator";
import { LoadingSkeleton } from "@/components/analytics/loading-skeleton";
import { useAnalyticsDashboardStore } from "@/stores/analytics-dashboard";
import {
    useCampaignDelivery,
    useDashboardOverview,
    useQueueHealth,
    useRecoveryAnalytics,
    useRetryAnalytics,
    useWebhookHealth,
} from "@/hooks/analytics/useDashboardQueries";
import { useDashboardRealtime } from "@/hooks/analytics/useDashboardRealtime";
import { Button } from "@/components/ui/button";

const periods = [
    { value: "last_7_days", label: "Last 7 days" },
    { value: "last_30_days", label: "Last 30 days" },
    { value: "last_90_days", label: "Last 90 days" },
];

export default function AnalyticsPage() {
    const [period, setPeriod] = useState("last_7_days");
    const [granularity, setGranularity] = useState("1h");
    const [startDate, setStartDate] = useState("");
    const [endDate, setEndDate] = useState("");

    const filters = useMemo(() => {
        return {
            period: startDate && endDate ? undefined : period,
            start_time: startDate || undefined,
            end_time: endDate || undefined,
            granularity,
        };
    }, [period, startDate, endDate, granularity]);

    const overviewQuery = useDashboardOverview(filters);
    const campaignQuery = useCampaignDelivery(filters);
    const queueQuery = useQueueHealth(filters);
    const webhookQuery = useWebhookHealth(filters);
    const retryQuery = useRetryAnalytics(filters);
    const recoveryQuery = useRecoveryAnalytics(filters);

    useDashboardRealtime();
    const { realtime, sseStatus, lastEventAt } = useAnalyticsDashboardStore();

    const timelineCampaign = (campaignQuery.data?.data?.timeline as any[]) || [];
    const queueTimeline = (queueQuery.data?.data?.timeline as any[]) || [];
    const webhookTimeline = (webhookQuery.data?.data?.timeline as any[]) || [];

    const refresh = () => {
        overviewQuery.refetch();
        campaignQuery.refetch();
        queueQuery.refetch();
        webhookQuery.refetch();
        retryQuery.refetch();
        recoveryQuery.refetch();
    };

    return (
        <PageLayout
            title="Analytics Dashboard"
            description="Operational insights across campaigns, queues, webhooks, workflows, and recovery pipelines."
            actions={<RealtimeIndicator status={sseStatus} lastEventAt={lastEventAt} />}
        >
            <div className="space-y-6">
                <div className="flex flex-wrap items-center gap-3">
                    <select
                        className="rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-950 px-3 py-2 text-sm"
                        value={period}
                        onChange={(e) => setPeriod(e.target.value)}
                    >
                        {periods.map((p) => (
                            <option key={p.value} value={p.value}>
                                {p.label}
                            </option>
                        ))}
                    </select>
                    <select
                        className="rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-950 px-3 py-2 text-sm"
                        value={granularity}
                        onChange={(e) => setGranularity(e.target.value)}
                    >
                        <option value="1h">Hourly</option>
                        <option value="1d">Daily</option>
                        <option value="1w">Weekly</option>
                    </select>
                    <input
                        type="date"
                        className="rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-950 px-3 py-2 text-sm"
                        value={startDate}
                        onChange={(e) => setStartDate(e.target.value)}
                    />
                    <input
                        type="date"
                        className="rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-950 px-3 py-2 text-sm"
                        value={endDate}
                        onChange={(e) => setEndDate(e.target.value)}
                    />
                    <Button variant="secondary" onClick={refresh}>
                        Refresh
                    </Button>
                    {(overviewQuery.isFetching || campaignQuery.isFetching) && (
                        <span className="text-xs text-gray-500">Refreshing...</span>
                    )}
                </div>

                <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                    {overviewQuery.isLoading ? (
                        <>
                            <LoadingSkeleton className="h-28" />
                            <LoadingSkeleton className="h-28" />
                            <LoadingSkeleton className="h-28" />
                            <LoadingSkeleton className="h-28" />
                        </>
                    ) : (
                        <>
                            <StatCard
                                label="Messages Sent"
                                value={overviewQuery.data?.data?.total_messages_sent ?? 0}
                                sublabel="Selected period"
                            />
                            <StatCard
                                label="Active Campaigns"
                                value={overviewQuery.data?.data?.campaigns_active ?? 0}
                                sublabel="Running now"
                            />
                            <StatCard
                                label="Queue Depth"
                                value={overviewQuery.data?.data?.queue_depth ?? 0}
                                sublabel="Pending tasks"
                            />
                            <StatCard
                                label="Delivery Rate"
                                value={`${overviewQuery.data?.data?.delivery_rate ?? 0}%`}
                                sublabel="Workspace"
                            />
                        </>
                    )}
                </section>

                <section className="grid gap-4 xl:grid-cols-2">
                    <ChartCard title="Campaign Delivery" description="Sent, delivered, failed">
                        {campaignQuery.isLoading ? (
                            <LoadingSkeleton className="h-56" />
                        ) : (
                            <ResponsiveContainer width="100%" height="100%">
                                <LineChart data={timelineCampaign}>
                                    <XAxis dataKey="timestamp" hide />
                                    <YAxis />
                                    <Tooltip />
                                    <Legend />
                                    <Line type="monotone" dataKey="sent" stroke="#2563eb" strokeWidth={2} />
                                    <Line type="monotone" dataKey="delivered" stroke="#10b981" strokeWidth={2} />
                                    <Line type="monotone" dataKey="failed" stroke="#ef4444" strokeWidth={2} />
                                </LineChart>
                            </ResponsiveContainer>
                        )}
                    </ChartCard>

                    <ChartCard title="Queue Health" description="Completed vs failed tasks">
                        {queueQuery.isLoading ? (
                            <LoadingSkeleton className="h-56" />
                        ) : (
                            <ResponsiveContainer width="100%" height="100%">
                                <BarChart data={queueTimeline}>
                                    <XAxis dataKey="timestamp" hide />
                                    <YAxis />
                                    <Tooltip />
                                    <Legend />
                                    <Bar dataKey="tasks_completed" fill="#22c55e" />
                                    <Bar dataKey="tasks_failed" fill="#ef4444" />
                                </BarChart>
                            </ResponsiveContainer>
                        )}
                    </ChartCard>
                </section>

                <section className="grid gap-4 xl:grid-cols-2">
                    <ChartCard title="Webhook Health" description="Received vs failed">
                        {webhookQuery.isLoading ? (
                            <LoadingSkeleton className="h-56" />
                        ) : (
                            <ResponsiveContainer width="100%" height="100%">
                                <LineChart data={webhookTimeline}>
                                    <XAxis dataKey="timestamp" hide />
                                    <YAxis />
                                    <Tooltip />
                                    <Legend />
                                    <Line type="monotone" dataKey="received" stroke="#38bdf8" strokeWidth={2} />
                                    <Line type="monotone" dataKey="failed" stroke="#f97316" strokeWidth={2} />
                                </LineChart>
                            </ResponsiveContainer>
                        )}
                    </ChartCard>

                    <ChartCard title="Recovery Metrics" description="Detected vs completed">
                        {recoveryQuery.isLoading ? (
                            <LoadingSkeleton className="h-56" />
                        ) : (
                            <ResponsiveContainer width="100%" height="100%">
                                <BarChart data={recoveryQuery.data?.data?.timeline || []}>
                                    <XAxis dataKey="timestamp" hide />
                                    <YAxis />
                                    <Tooltip />
                                    <Legend />
                                    <Bar dataKey="detected" fill="#6366f1" />
                                    <Bar dataKey="completed" fill="#22c55e" />
                                </BarChart>
                            </ResponsiveContainer>
                        )}
                    </ChartCard>
                </section>

                <section className="grid gap-4 xl:grid-cols-3">
                    <ChartCard title="Retry Analytics" description="Retry attempts">
                        {retryQuery.isLoading ? (
                            <LoadingSkeleton className="h-56" />
                        ) : (
                            <ResponsiveContainer width="100%" height="100%">
                                <LineChart data={retryQuery.data?.data?.timeline || []}>
                                    <XAxis dataKey="timestamp" hide />
                                    <YAxis />
                                    <Tooltip />
                                    <Line type="monotone" dataKey="retry_attempts" stroke="#f59e0b" strokeWidth={2} />
                                </LineChart>
                            </ResponsiveContainer>
                        )}
                    </ChartCard>

                    <ChartCard title="Queue Health Score" description="Success and failure rates">
                        <div className="space-y-3">
                            <HealthIndicator label="Success Rate" value={queueQuery.data?.data?.summary?.success_rate ?? 0} />
                            <HealthIndicator
                                label="Failure Rate"
                                value={queueQuery.data?.data?.summary?.failure_rate ?? 0}
                                direction="lower"
                            />
                        </div>
                    </ChartCard>

                    <ChartCard title="Realtime Counters" description="Live throughput">
                        {realtime ? (
                            <div className="grid grid-cols-2 gap-3 text-sm">
                                <div>
                                    <p className="text-xs text-gray-500">Active campaigns</p>
                                    <p className="text-lg font-semibold">{realtime.active_campaigns}</p>
                                </div>
                                <div>
                                    <p className="text-xs text-gray-500">Queue depth</p>
                                    <p className="text-lg font-semibold">{realtime.queue_depth}</p>
                                </div>
                                <div>
                                    <p className="text-xs text-gray-500">Messages/min</p>
                                    <p className="text-lg font-semibold">{realtime.messages_last_minute}</p>
                                </div>
                                <div>
                                    <p className="text-xs text-gray-500">Active workers</p>
                                    <p className="text-lg font-semibold">{realtime.active_workers}</p>
                                </div>
                            </div>
                        ) : (
                            <LoadingSkeleton className="h-32" />
                        )}
                    </ChartCard>
                </section>

                <section className="grid gap-4 xl:grid-cols-2">
                    <ChartCard title="Webhook Failures" description="Recent errors" contentClassName="h-auto">
                        <MetricsTable
                            columns={[
                                { key: "source", header: "Source" },
                                { key: "error_message", header: "Error" },
                                { key: "received_at", header: "Time" },
                            ]}
                            data={webhookQuery.data?.data?.recent_failures || []}
                            emptyText="No recent webhook failures"
                        />
                    </ChartCard>

                    <ChartCard title="Recovery Activity" description="Recent recovery events" contentClassName="h-auto">
                        <MetricsTable
                            columns={[
                                { key: "campaign_id", header: "Campaign" },
                                { key: "status", header: "Status" },
                                { key: "started_at", header: "Started" },
                            ]}
                            data={recoveryQuery.data?.data?.recent_recoveries || []}
                            emptyText="No recovery activity"
                        />
                    </ChartCard>
                </section>
            </div>
        </PageLayout>
    );
}
