import { useEffect, useMemo } from "react";
import { useWorkflowBuilderStore } from "@/stores/workflow-builder";
import { workflowRuntimeService } from "@/services/workflow/workflow-runtime";

function debounce<T extends (...args: any[]) => void>(fn: T, delay: number) {
    let timeout: ReturnType<typeof setTimeout> | null = null;
    return (...args: Parameters<T>) => {
        if (timeout) {
            clearTimeout(timeout);
        }
        timeout = setTimeout(() => fn(...args), delay);
    };
}

export function useWorkflowAutosave() {
    const {
        workflowId,
        name,
        description,
        nodes,
        edges,
        isDirty,
        setSaving,
        setDirty,
        setLastSavedAt,
    } = useWorkflowBuilderStore();

    const payload = useMemo(() => {
        const nodesPayload = nodes.map((node) => ({
            node_id: node.id,
            node_type: node.type || "trigger",
            name: node.data?.name || node.id,
            config: node.data?.config || {},
            position: node.position,
        }));

        const edgesPayload = edges.map((edge) => ({
            edge_id: edge.id,
            source_node_id: edge.source,
            target_node_id: edge.target,
            condition: typeof edge.label === "string" ? edge.label : undefined,
        }));

        return { name, description, nodes: nodesPayload, edges: edgesPayload };
    }, [name, description, nodes, edges]);

    useEffect(() => {
        if (!workflowId || !isDirty) return;

        const save = debounce(async () => {
            try {
                setSaving(true);
                await workflowRuntimeService.updateWorkflow(workflowId, payload);
                setDirty(false);
                setLastSavedAt(new Date().toISOString());
            } finally {
                setSaving(false);
            }
        }, 1200);

        save();
    }, [workflowId, payload, isDirty, setSaving, setDirty, setLastSavedAt]);
}
