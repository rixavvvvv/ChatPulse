import React, { useCallback } from "react";
import {
    addEdge,
    Connection,
    Edge,
    Node,
    OnConnect,
    OnEdgesChange,
    OnNodesChange,
    applyEdgeChanges,
    applyNodeChanges,
} from "reactflow";
import { useWorkflowBuilderStore } from "@/stores/workflow-builder";
import { WorkflowDefinitionResponse } from "@/types";

export function useWorkflowBuilder() {
    const {
        nodes,
        edges,
        setNodes,
        setEdges,
        setSelectedNode,
        addNode,
        loadFromDefinition,
    } = useWorkflowBuilderStore();

    const onNodesChange: OnNodesChange = useCallback(
        (changes) => setNodes(applyNodeChanges(changes, nodes)),
        [nodes, setNodes]
    );

    const onEdgesChange: OnEdgesChange = useCallback(
        (changes) => setEdges(applyEdgeChanges(changes, edges)),
        [edges, setEdges]
    );

    const onConnect: OnConnect = useCallback(
        (connection: Connection) => setEdges(addEdge(connection, edges)),
        [edges, setEdges]
    );

    const onNodeClick = useCallback(
        (_: unknown, node: Node) => setSelectedNode(node.id),
        [setSelectedNode]
    );

    const handleDrop = useCallback(
        (event: React.DragEvent, reactFlowInstance: any) => {
            event.preventDefault();
            const nodeType = event.dataTransfer.getData("application/reactflow");
            if (!nodeType) return;

            const position = reactFlowInstance.project({
                x: event.clientX - 260,
                y: event.clientY - 120,
            });
            addNode(nodeType as any, position);
        },
        [addNode]
    );

    const handleLoadDefinition = useCallback(
        (definition: WorkflowDefinitionResponse) => {
            loadFromDefinition({
                id: definition.id,
                name: definition.name,
                description: definition.description,
                nodes: definition.nodes,
                edges: definition.edges,
            });
        },
        [loadFromDefinition]
    );

    return {
        nodes,
        edges,
        onNodesChange,
        onEdgesChange,
        onConnect,
        onNodeClick,
        handleDrop,
        handleLoadDefinition,
    };
}
