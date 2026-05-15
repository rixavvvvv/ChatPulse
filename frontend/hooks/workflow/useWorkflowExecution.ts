import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { workflowRuntimeService } from "@/services/workflow/workflow-runtime";
import { useWorkflowBuilderStore } from "@/stores/workflow-builder";

export function useWorkflowExecution(executionId?: string) {
    const setExecution = useWorkflowBuilderStore((state) => state.setExecution);
    const setExecutionStatus = useWorkflowBuilderStore((state) => state.setExecutionStatus);
    const setTraversalPath = useWorkflowBuilderStore((state) => state.setTraversalPath);
    const setNodeErrors = useWorkflowBuilderStore((state) => state.setNodeErrors);

    const query = useQuery({
        queryKey: ["workflow", "execution", executionId],
        queryFn: () => workflowRuntimeService.getExecution(executionId as string),
        enabled: !!executionId,
        refetchInterval: 4000,
    });

    useEffect(() => {
        if (!query.data?.data) return;
        const execution = query.data.data;
        setExecution(execution);
        setExecutionStatus(execution.status);

        const traversal = execution.node_executions?.map((node) => node.node_id) || [];
        setTraversalPath(traversal);

        const errors: Record<string, string> = {};
        execution.node_executions?.forEach((node) => {
            if (node.error) {
                errors[node.node_id] = node.error;
            }
        });
        setNodeErrors(errors);
    }, [query.data, setExecution, setExecutionStatus, setTraversalPath, setNodeErrors]);

    return query;
}
