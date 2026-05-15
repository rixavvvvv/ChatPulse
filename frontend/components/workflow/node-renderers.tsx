import React from "react";
import { Handle, Position } from "reactflow";
import { cn } from "@/lib/utils";

interface NodeProps {
    data: {
        name?: string;
        config?: Record<string, unknown>;
        isError?: boolean;
        isActive?: boolean;
    };
}

function NodeShell({ title, subtitle, isError, isActive }: { title: string; subtitle: string; isError?: boolean; isActive?: boolean }) {
    return (
        <div
            className={cn(
                "rounded-xl border px-3 py-2 text-xs bg-white dark:bg-gray-950 shadow-sm",
                isActive && "border-blue-600 ring-2 ring-blue-200 dark:ring-blue-900",
                isError && "border-red-500"
            )}
        >
            <div className="font-semibold text-sm">{title}</div>
            <div className="text-[11px] text-gray-500 dark:text-gray-400">{subtitle}</div>
        </div>
    );
}

export function TriggerNode({ data }: NodeProps) {
    return (
        <div>
            <Handle type="source" position={Position.Right} />
            <NodeShell title={data.name || "Trigger"} subtitle="Start" isError={data.isError} isActive={data.isActive} />
        </div>
    );
}

export function ConditionNode({ data }: NodeProps) {
    return (
        <div>
            <Handle type="target" position={Position.Left} />
            <Handle type="source" position={Position.Right} />
            <NodeShell title={data.name || "Condition"} subtitle="Branching" isError={data.isError} isActive={data.isActive} />
        </div>
    );
}

export function DelayNode({ data }: NodeProps) {
    return (
        <div>
            <Handle type="target" position={Position.Left} />
            <Handle type="source" position={Position.Right} />
            <NodeShell title={data.name || "Delay"} subtitle="Wait" isError={data.isError} isActive={data.isActive} />
        </div>
    );
}

export function SendMessageNode({ data }: NodeProps) {
    return (
        <div>
            <Handle type="target" position={Position.Left} />
            <Handle type="source" position={Position.Right} />
            <NodeShell title={data.name || "Send Message"} subtitle="Outbound" isError={data.isError} isActive={data.isActive} />
        </div>
    );
}

export function AddTagNode({ data }: NodeProps) {
    return (
        <div>
            <Handle type="target" position={Position.Left} />
            <Handle type="source" position={Position.Right} />
            <NodeShell title={data.name || "Add Tag"} subtitle="Contact" isError={data.isError} isActive={data.isActive} />
        </div>
    );
}

export function RemoveTagNode({ data }: NodeProps) {
    return (
        <div>
            <Handle type="target" position={Position.Left} />
            <Handle type="source" position={Position.Right} />
            <NodeShell title={data.name || "Remove Tag"} subtitle="Contact" isError={data.isError} isActive={data.isActive} />
        </div>
    );
}

export function BranchNode({ data }: NodeProps) {
    return (
        <div>
            <Handle type="target" position={Position.Left} />
            <Handle type="source" position={Position.Right} />
            <NodeShell title={data.name || "Branch"} subtitle="Split" isError={data.isError} isActive={data.isActive} />
        </div>
    );
}

export function WebhookCallNode({ data }: NodeProps) {
    return (
        <div>
            <Handle type="target" position={Position.Left} />
            <Handle type="source" position={Position.Right} />
            <NodeShell title={data.name || "Webhook"} subtitle="HTTP" isError={data.isError} isActive={data.isActive} />
        </div>
    );
}
