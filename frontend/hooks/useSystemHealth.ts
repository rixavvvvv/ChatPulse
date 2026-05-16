"use client";

import { useQuery } from "@tanstack/react-query";

interface RedisHealth {
    status: string;
    latency_ms?: number;
    connected: boolean;
    version?: string;
    used_memory_mb?: number;
    connected_clients?: number;
    total_keys?: number;
    error?: string;
}

interface PostgresHealth {
    status: string;
    latency_ms?: number;
    connected: boolean;
    workflow_executions?: number;
    delayed_executions?: number;
    failed_jobs?: number;
    error?: string;
}

interface CeleryHealth {
    status: string;
    reachable: boolean;
    workers_online?: number;
    active_tasks?: number;
    max_workers?: number;
    error?: string;
}

interface WebSocketHealth {
    status: string;
    active_connections?: number;
    active_rooms?: number;
    connected: boolean;
    error?: string;
}

interface QueueHealth {
    status: string;
    queues?: Record<string, { depth: number; scheduled: number }>;
    error?: string;
}

interface FailedJobs {
    total?: number;
    last_hour?: number;
    error?: string;
}

interface DelayedExecutions {
    pending?: number;
    overdue?: number;
    error?: string;
}

interface WorkflowFailures {
    total_failed?: number;
    last_hour?: number;
    error?: string;
}

export interface SystemHealth {
    timestamp: string;
    overall_status: string;
    redis: RedisHealth;
    postgresql: PostgresHealth;
    celery: CeleryHealth;
    websocket: WebSocketHealth;
    queues: QueueHealth;
    failed_jobs: FailedJobs;
    delayed_executions: DelayedExecutions;
    workflow_failures: WorkflowFailures;
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

async function fetchSystemHealth(): Promise<SystemHealth> {
    const response = await fetch(`${API_URL}/admin/system-health`);
    if (!response.ok) {
        throw new Error("Failed to fetch system health");
    }
    return response.json();
}

export function useSystemHealth(enabled = true) {
    return useQuery({
        queryKey: ["system-health"],
        queryFn: fetchSystemHealth,
        refetchInterval: 10000, // Refresh every 10 seconds
        enabled,
    });
}