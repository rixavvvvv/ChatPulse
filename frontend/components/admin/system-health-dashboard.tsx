"use client";

import React, { useState } from "react";
import { useSystemHealth, SystemHealth } from "@/hooks/useSystemHealth";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

function StatusBadge({ status }: { status: string }) {
    const colors = {
        healthy: "bg-green-500",
        degraded: "bg-yellow-500",
        unhealthy: "bg-red-500",
    };
    return (
        <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium text-white ${colors[status as keyof typeof colors] || "bg-gray-500"}`}>
            {status}
        </span>
    );
}

function HealthCard({ title, children, alert }: { title: string; children: React.ReactNode; alert?: boolean }) {
    return (
        <Card className={alert ? "border-red-500 dark:border-red-500" : ""}>
            <CardHeader className="py-3">
                <CardTitle className="text-sm font-medium">{title}</CardTitle>
            </CardHeader>
            <CardContent className="py-2">{children}</CardContent>
        </Card>
    );
}

function MetricRow({ label, value, unit = "", warning = false }: { label: string; value: number | string; unit?: string; warning?: boolean }) {
    return (
        <div className="flex justify-between text-sm">
            <span className="text-gray-500 dark:text-gray-400">{label}</span>
            <span className={warning ? "text-yellow-600 dark:text-yellow-400" : "text-gray-900 dark:text-gray-100"}>
                {value}{unit}
            </span>
        </div>
    );
}

function RedisPanel({ health }: { health: SystemHealth["redis"] }) {
    return (
        <HealthCard title="Redis" alert={health.status !== "healthy"}>
            <div className="space-y-1">
                <div className="flex justify-between items-center mb-2">
                    <StatusBadge status={health.status} />
                    <span className="text-xs text-gray-500">{health.latency_ms}ms</span>
                </div>
                {health.connected && (
                    <>
                        <MetricRow label="Version" value={health.version || "N/A"} />
                        <MetricRow label="Memory" value={health.used_memory_mb || 0} unit=" MB" />
                        <MetricRow label="Clients" value={health.connected_clients || 0} />
                        <MetricRow label="Keys" value={health.total_keys || 0} />
                    </>
                )}
                {health.error && <p className="text-xs text-red-500">{health.error}</p>}
            </div>
        </HealthCard>
    );
}

function PostgresPanel({ health }: { health: SystemHealth["postgresql"] }) {
    return (
        <HealthCard title="PostgreSQL" alert={health.status !== "healthy"}>
            <div className="space-y-1">
                <div className="flex justify-between items-center mb-2">
                    <StatusBadge status={health.status} />
                    <span className="text-xs text-gray-500">{health.latency_ms}ms</span>
                </div>
                {health.connected && (
                    <>
                        <MetricRow label="Workflows" value={health.workflow_executions || 0} />
                        <MetricRow label="Delayed" value={health.delayed_executions || 0} />
                        <MetricRow label="Failed Jobs" value={health.failed_jobs || 0} warning={(health.failed_jobs || 0) > 10} />
                    </>
                )}
                {health.error && <p className="text-xs text-red-500">{health.error}</p>}
            </div>
        </HealthCard>
    );
}

function CeleryPanel({ health }: { health: SystemHealth["celery"] }) {
    return (
        <HealthCard title="Celery Workers" alert={health.status !== "healthy"}>
            <div className="space-y-1">
                <div className="flex justify-between items-center mb-2">
                    <StatusBadge status={health.status} />
                </div>
                {health.reachable ? (
                    <>
                        <MetricRow label="Workers" value={health.workers_online || 0} />
                        <MetricRow label="Active Tasks" value={health.active_tasks || 0} warning={(health.active_tasks || 0) > 50} />
                        <MetricRow label="Max Workers" value={health.max_workers || 0} />
                    </>
                ) : (
                    <p className="text-xs text-red-500">{health.error || "Workers unreachable"}</p>
                )}
            </div>
        </HealthCard>
    );
}

function WebSocketPanel({ health }: { health: SystemHealth["websocket"] }) {
    return (
        <HealthCard title="WebSocket" alert={health.status !== "healthy"}>
            <div className="space-y-1">
                <div className="flex justify-between items-center mb-2">
                    <StatusBadge status={health.status} />
                </div>
                {health.connected && (
                    <>
                        <MetricRow label="Connections" value={health.active_connections || 0} />
                        <MetricRow label="Rooms" value={health.active_rooms || 0} />
                    </>
                )}
                {health.error && <p className="text-xs text-red-500">{health.error}</p>}
            </div>
        </HealthCard>
    );
}

function QueuesPanel({ health }: { health: SystemHealth["queues"] }) {
    const queues = health.queues || {};
    return (
        <HealthCard title="Queue Health" alert={health.status !== "healthy"}>
            <div className="space-y-1">
                <div className="flex justify-between items-center mb-2">
                    <StatusBadge status={health.status} />
                </div>
                {Object.entries(queues).map(([name, stats]) => (
                    <div key={name} className="flex justify-between text-sm">
                        <span className="text-gray-500 dark:text-gray-400">{name}</span>
                        <span className={(stats.depth || 0) > 50 ? "text-yellow-600 dark:text-yellow-400" : "text-gray-900 dark:text-gray-100"}>
                            {stats.depth || 0} pending
                        </span>
                    </div>
                ))}
                {health.error && <p className="text-xs text-red-500">{health.error}</p>}
            </div>
        </HealthCard>
    );
}

function FailedJobsPanel({ data }: { data: SystemHealth["failed_jobs"] }) {
    const hasAlerts = (data?.last_hour || 0) > 5;
    return (
        <HealthCard title="Failed Jobs" alert={hasAlerts}>
            <div className="space-y-1">
                <MetricRow label="Total" value={data?.total || 0} warning={(data?.total || 0) > 20} />
                <MetricRow label="Last Hour" value={data?.last_hour || 0} warning={(data?.last_hour || 0) > 5} />
            </div>
        </HealthCard>
    );
}

function DelayedExecutionsPanel({ data }: { data: SystemHealth["delayed_executions"] }) {
    const hasAlerts = (data?.overdue || 0) > 0;
    return (
        <HealthCard title="Delayed Executions" alert={hasAlerts}>
            <div className="space-y-1">
                <MetricRow label="Pending" value={data?.pending || 0} />
                <MetricRow label="Overdue" value={data?.overdue || 0} warning={(data?.overdue || 0) > 0} />
            </div>
        </HealthCard>
    );
}

function WorkflowFailuresPanel({ data }: { data: SystemHealth["workflow_failures"] }) {
    const hasAlerts = (data?.last_hour || 0) > 3;
    return (
        <HealthCard title="Workflow Failures" alert={hasAlerts}>
            <div className="space-y-1">
                <MetricRow label="Total Failed" value={data?.total_failed || 0} warning={(data?.total_failed || 0) > 10} />
                <MetricRow label="Last Hour" value={data?.last_hour || 0} warning={(data?.last_hour || 0) > 3} />
            </div>
        </HealthCard>
    );
}

export function SystemHealthDashboard() {
    const { data: health, isLoading, error, refetch, isFetching } = useSystemHealth();
    const [autoRefresh, setAutoRefresh] = useState(true);

    if (isLoading) {
        return (
            <div className="flex items-center justify-center p-8">
                <div className="text-gray-500">Loading system health...</div>
            </div>
        );
    }

    if (error) {
        return (
            <div className="p-4">
                <Card className="border-red-500">
                    <CardContent className="py-4">
                        <p className="text-red-500">Failed to load system health: {(error as Error).message}</p>
                        <Button onClick={() => refetch()} className="mt-2">
                            Retry
                        </Button>
                    </CardContent>
                </Card>
            </div>
        );
    }

    if (!health) {
        return null;
    }

    const alerts: string[] = [];
    if (health.redis.status !== "healthy") alerts.push("Redis unhealthy");
    if (health.postgresql.status !== "healthy") alerts.push("PostgreSQL unhealthy");
    if (health.celery.status !== "healthy") alerts.push("Celery workers unhealthy");
    if (health.websocket.status !== "healthy") alerts.push("WebSocket unhealthy");
    if ((health.failed_jobs.last_hour || 0) > 5) alerts.push(`${health.failed_jobs.last_hour} failed jobs in last hour`);
    if ((health.delayed_executions.overdue || 0) > 0) alerts.push(`${health.delayed_executions.overdue} overdue delayed executions`);
    if ((health.workflow_failures.last_hour || 0) > 3) alerts.push(`${health.workflow_failures.last_hour} workflow failures in last hour`);

    return (
        <div className="space-y-4">
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                    <h2 className="text-lg font-semibold">System Health</h2>
                    <StatusBadge status={health.overall_status} />
                    {isFetching && <span className="text-xs text-gray-500">Refreshing...</span>}
                </div>
                <div className="flex gap-2">
                    <Button
                        variant={autoRefresh ? "default" : "outline"}
                        size="sm"
                        onClick={() => setAutoRefresh(!autoRefresh)}
                    >
                        Auto: {autoRefresh ? "On" : "Off"}
                    </Button>
                    <Button variant="outline" size="sm" onClick={() => refetch()}>
                        Refresh
                    </Button>
                </div>
            </div>

            {alerts.length > 0 && (
                <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-3">
                    <div className="text-sm font-medium text-red-800 dark:text-red-200 mb-1">
                        Alerts ({alerts.length})
                    </div>
                    <ul className="text-xs text-red-700 dark:text-red-300 space-y-1">
                        {alerts.map((alert, i) => (
                            <li key={i}>• {alert}</li>
                        ))}
                    </ul>
                </div>
            )}

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                <RedisPanel health={health.redis} />
                <PostgresPanel health={health.postgresql} />
                <CeleryPanel health={health.celery} />
                <WebSocketPanel health={health.websocket} />
                <QueuesPanel health={health.queues} />
                <FailedJobsPanel data={health.failed_jobs} />
                <DelayedExecutionsPanel data={health.delayed_executions} />
                <WorkflowFailuresPanel data={health.workflow_failures} />
            </div>

            <div className="text-xs text-gray-500 text-center">
                Last updated: {health.timestamp ? new Date(health.timestamp).toLocaleString() : "N/A"}
            </div>
        </div>
    );
}