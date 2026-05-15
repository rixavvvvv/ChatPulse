"use client";

import React, { useMemo, useState } from "react";
import ReactFlow, {
    Background,
    Controls,
    MiniMap,
    ReactFlowInstance,
} from "reactflow";
import "reactflow/dist/style.css";

import { useWorkflowBuilder } from "@/hooks/workflow/useWorkflowBuilder";
import { useWorkflowBuilderStore } from "@/stores/workflow-builder";
import {
    AddTagNode,
    BranchNode,
    ConditionNode,
    DelayNode,
    RemoveTagNode,
    SendMessageNode,
    TriggerNode,
    WebhookCallNode,
} from "@/components/workflow/node-renderers";

const nodeTypes = {
    trigger: TriggerNode,
    condition: ConditionNode,
    delay: DelayNode,
    send_message: SendMessageNode,
    add_tag: AddTagNode,
    remove_tag: RemoveTagNode,
    branch: BranchNode,
    webhook_call: WebhookCallNode,
};

interface BuilderCanvasProps {
    onInit?: (instance: ReactFlowInstance) => void;
}

export function BuilderCanvas({ onInit }: BuilderCanvasProps) {
    const { nodes, edges, onNodesChange, onEdgesChange, onConnect, onNodeClick, handleDrop } =
        useWorkflowBuilder();
    const { traversalPath, nodeErrors } = useWorkflowBuilderStore();
    const [instance, setInstance] = useState<ReactFlowInstance | null>(null);

    const annotatedNodes = useMemo(() => {
        return nodes.map((node) => ({
            ...node,
            data: {
                ...node.data,
                isActive: traversalPath.includes(node.id),
                isError: nodeErrors[node.id],
            },
        }));
    }, [nodes, traversalPath, nodeErrors]);

    return (
        <div
            className="h-full w-full"
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => instance && handleDrop(e, instance)}
        >
            <ReactFlow
                nodes={annotatedNodes}
                edges={edges}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                onConnect={onConnect}
                onNodeClick={onNodeClick}
                nodeTypes={nodeTypes}
                fitView
                onInit={(flowInstance) => {
                    setInstance(flowInstance);
                    onInit?.(flowInstance);
                }}
            >
                <MiniMap />
                <Controls />
                <Background gap={20} size={1} />
            </ReactFlow>
        </div>
    );
}
