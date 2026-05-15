import { create } from "zustand";
import { Edge, Node } from "reactflow";
import {
    WorkflowDefinitionEdge,
    WorkflowDefinitionNode,
    WorkflowExecutionDetailResponse,
    WorkflowExecutionStatus,
    WorkflowNodeType,
    WorkflowValidationError,
} from "@/types";

export interface WorkflowBuilderState {
    workflowId?: number;
    name: string;
    description: string;
    nodes: Node[];
    edges: Edge[];
    selectedNodeId?: string | null;
    isDirty: boolean;
    isSaving: boolean;
    lastSavedAt?: string | null;
    validationErrors: WorkflowValidationError[];
    execution?: WorkflowExecutionDetailResponse | null;
    executionStatus?: WorkflowExecutionStatus | null;
    traversalPath: string[];
    nodeErrors: Record<string, string>;
    nodeSearch: string;
    setWorkflowMeta: (name: string, description: string) => void;
    setNodes: (nodes: Node[]) => void;
    setEdges: (edges: Edge[]) => void;
    setSelectedNode: (nodeId?: string | null) => void;
    setDirty: (isDirty: boolean) => void;
    setSaving: (isSaving: boolean) => void;
    setLastSavedAt: (timestamp?: string | null) => void;
    setValidationErrors: (errors: WorkflowValidationError[]) => void;
    setExecution: (execution?: WorkflowExecutionDetailResponse | null) => void;
    setExecutionStatus: (status?: WorkflowExecutionStatus | null) => void;
    setTraversalPath: (nodeIds: string[]) => void;
    setNodeErrors: (errors: Record<string, string>) => void;
    setNodeSearch: (query: string) => void;
    loadFromDefinition: (definition: {
        id: number;
        name: string;
        description?: string | null;
        nodes: WorkflowDefinitionNode[];
        edges: WorkflowDefinitionEdge[];
    }) => void;
    addNode: (nodeType: WorkflowNodeType, position: { x: number; y: number }) => void;
}

export const useWorkflowBuilderStore = create<WorkflowBuilderState>((set, get) => ({
    name: "Untitled Workflow",
    description: "",
    nodes: [],
    edges: [],
    selectedNodeId: null,
    isDirty: false,
    isSaving: false,
    lastSavedAt: null,
    validationErrors: [],
    execution: null,
    executionStatus: null,
    traversalPath: [],
    nodeErrors: {},
    nodeSearch: "",
    setWorkflowMeta: (name, description) => set({ name, description, isDirty: true }),
    setNodes: (nodes) => set({ nodes, isDirty: true }),
    setEdges: (edges) => set({ edges, isDirty: true }),
    setSelectedNode: (nodeId) => set({ selectedNodeId: nodeId ?? null }),
    setDirty: (isDirty) => set({ isDirty }),
    setSaving: (isSaving) => set({ isSaving }),
    setLastSavedAt: (timestamp) => set({ lastSavedAt: timestamp ?? null }),
    setValidationErrors: (errors) => set({ validationErrors: errors }),
    setExecution: (execution) => set({ execution: execution ?? null }),
    setExecutionStatus: (status) => set({ executionStatus: status ?? null }),
    setTraversalPath: (nodeIds) => set({ traversalPath: nodeIds }),
    setNodeErrors: (errors) => set({ nodeErrors: errors }),
    setNodeSearch: (query) => set({ nodeSearch: query }),
    loadFromDefinition: (definition) => {
        const nodes: Node[] = definition.nodes.map((node) => ({
            id: node.node_id,
            type: node.node_type,
            position: node.position,
            data: {
                name: node.name,
                config: node.config,
            },
        }));

        const edges: Edge[] = definition.edges.map((edge) => ({
            id: edge.edge_id,
            source: edge.source_node_id,
            target: edge.target_node_id,
            label: edge.condition || undefined,
        }));

        set({
            workflowId: definition.id,
            name: definition.name,
            description: definition.description || "",
            nodes,
            edges,
            isDirty: false,
        });
    },
    addNode: (nodeType, position) => {
        const id = `${nodeType}-${Date.now()}`;
        const node: Node = {
            id,
            type: nodeType,
            position,
            data: {
                name: `${nodeType.replace("_", " ")}`,
                config: {},
            },
        };

        set((state) => ({
            nodes: [...state.nodes, node],
            isDirty: true,
        }));
    },
}));
