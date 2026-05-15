import { useMemo } from "react";
import { Edge, Node } from "reactflow";
import { WorkflowValidationError } from "@/types";

export function useWorkflowValidation(nodes: Node[], edges: Edge[]) {
    return useMemo(() => {
        const errors: WorkflowValidationError[] = [];
        const triggerNodes = nodes.filter((node) => node.type === "trigger");

        if (nodes.length === 0) {
            errors.push({
                error_type: "no_nodes",
                message: "Workflow has no nodes.",
                node_ids: [],
            });
            return errors;
        }

        if (triggerNodes.length === 0) {
            errors.push({
                error_type: "no_trigger_node",
                message: "Add at least one trigger node.",
                node_ids: [],
            });
        }

        if (triggerNodes.length > 1) {
            errors.push({
                error_type: "multiple_triggers",
                message: "Multiple trigger nodes detected. Use only one trigger.",
                node_ids: triggerNodes.map((node) => node.id),
            });
        }

        const nodeIds = new Set(nodes.map((node) => node.id));
        edges.forEach((edge) => {
            if (!nodeIds.has(edge.source) || !nodeIds.has(edge.target)) {
                errors.push({
                    error_type: "invalid_edge",
                    message: `Edge ${edge.id} references missing nodes.`,
                    node_ids: [edge.source, edge.target],
                });
            }
        });

        const orphanNodes = nodes.filter(
            (node) =>
                !edges.some((edge) => edge.source === node.id || edge.target === node.id)
        );

        orphanNodes.forEach((node) => {
            errors.push({
                error_type: "orphan_node",
                message: `Node ${node.data?.name || node.id} is not connected.`,
                node_ids: [node.id],
            });
        });

        return errors;
    }, [nodes, edges]);
}
