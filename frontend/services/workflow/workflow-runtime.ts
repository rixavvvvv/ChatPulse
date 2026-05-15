import { apiClient } from "@/services/api";
import {
    WorkflowDefinitionResponse,
    WorkflowExecutionDetailResponse,
    WorkflowExecutionResponse,
} from "@/types";

export interface WorkflowUpsertPayload {
    name?: string;
    description?: string;
    nodes?: Array<{
        node_id: string;
        node_type: string;
        name: string;
        config: Record<string, unknown>;
        position: { x: number; y: number };
    }>;
    edges?: Array<{
        edge_id: string;
        source_node_id: string;
        target_node_id: string;
        condition?: string | null;
    }>;
    status?: string;
}

export const workflowRuntimeService = {
    getWorkflow: (workflowId: number) =>
        apiClient.get<WorkflowDefinitionResponse>(`/workflows/${workflowId}`),

    updateWorkflow: (workflowId: number, payload: WorkflowUpsertPayload) =>
        apiClient.patch<WorkflowDefinitionResponse>(`/workflows/${workflowId}`, payload),

    createWorkflow: (payload: WorkflowUpsertPayload) =>
        apiClient.post<WorkflowDefinitionResponse>("/workflows", payload),

    triggerWorkflow: (workflowId: number, triggerData: Record<string, unknown>) =>
        apiClient.post<WorkflowExecutionResponse>(`/workflows/${workflowId}/trigger`, {
            trigger_type: "manual",
            trigger_data: triggerData,
        }),

    listExecutions: (workflowId: number, status?: string) =>
        apiClient.get<WorkflowExecutionResponse[]>(`/workflows/${workflowId}/executions`, {
            params: { status },
        }),

    getExecution: (executionId: string) =>
        apiClient.get<WorkflowExecutionDetailResponse>(`/workflows/executions/${executionId}`),
};
