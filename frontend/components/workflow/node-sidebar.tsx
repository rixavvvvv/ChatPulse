import React, { useMemo } from "react";
import { Input } from "@/components/ui/input";
import { useWorkflowBuilderStore } from "@/stores/workflow-builder";
import { WorkflowNodeType } from "@/types";

const nodeCatalog: Array<{ type: WorkflowNodeType; label: string; description: string }> = [
    { type: "trigger", label: "Trigger", description: "Start the workflow" },
    { type: "condition", label: "Condition", description: "Branch on rules" },
    { type: "delay", label: "Delay", description: "Wait for time" },
    { type: "send_message", label: "Send Message", description: "Outbound message" },
    { type: "add_tag", label: "Add Tag", description: "Tag contact" },
    { type: "remove_tag", label: "Remove Tag", description: "Remove tag" },
    { type: "branch", label: "Branch", description: "Split flow" },
    { type: "webhook_call", label: "Webhook Call", description: "HTTP callout" },
];

export function NodeSidebar() {
    const { nodeSearch, setNodeSearch } = useWorkflowBuilderStore();

    const filtered = useMemo(() => {
        if (!nodeSearch) return nodeCatalog;
        const query = nodeSearch.toLowerCase();
        return nodeCatalog.filter(
            (node) =>
                node.label.toLowerCase().includes(query) ||
                node.description.toLowerCase().includes(query)
        );
    }, [nodeSearch]);

    return (
        <aside className="w-full md:w-64 border-r border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-950 p-4 space-y-4">
            <div>
                <h3 className="text-sm font-semibold">Nodes</h3>
                <p className="text-xs text-gray-500">Drag to canvas</p>
            </div>
            <Input
                placeholder="Search nodes..."
                value={nodeSearch}
                onChange={(e) => setNodeSearch(e.target.value)}
            />
            <div className="space-y-2">
                {filtered.map((node) => (
                    <div
                        key={node.type}
                        draggable
                        onDragStart={(event) => {
                            event.dataTransfer.setData("application/reactflow", node.type);
                            event.dataTransfer.effectAllowed = "move";
                        }}
                        className="rounded-lg border border-gray-200 dark:border-gray-800 px-3 py-2 cursor-grab active:cursor-grabbing hover:bg-gray-50 dark:hover:bg-gray-900"
                    >
                        <p className="text-sm font-semibold">{node.label}</p>
                        <p className="text-xs text-gray-500">{node.description}</p>
                    </div>
                ))}
                {filtered.length === 0 && (
                    <p className="text-xs text-gray-500">No nodes match your search.</p>
                )}
            </div>
        </aside>
    );
}
