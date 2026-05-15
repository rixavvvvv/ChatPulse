import { useMutation, useQuery } from "@tanstack/react-query";
import { workflowRuntimeService } from "@/services/workflow/workflow-runtime";

export function useWorkflowDefinition(workflowId?: number) {
    return useQuery({
        queryKey: ["workflow", "definition", workflowId],
        queryFn: () => workflowRuntimeService.getWorkflow(workflowId as number),
        enabled: !!workflowId,
    });
}

export function useTriggerWorkflow() {
    return useMutation({
        mutationFn: ({ workflowId, triggerData }: { workflowId: number; triggerData: Record<string, unknown> }) =>
            workflowRuntimeService.triggerWorkflow(workflowId, triggerData),
    });
}

export function useWorkflowExecutions(workflowId?: number) {
    return useQuery({
        queryKey: ["workflow", "executions", workflowId],
        queryFn: () => workflowRuntimeService.listExecutions(workflowId as number),
        enabled: !!workflowId,
        refetchInterval: 8000,
    });
}
