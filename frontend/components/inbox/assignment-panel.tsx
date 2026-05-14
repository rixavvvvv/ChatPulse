import React from "react";
import { Button } from "@/components/ui/button";

interface AgentOption {
    id: number;
    name: string;
}

interface AssignmentPanelProps {
    assignedAgentId?: number | null;
    agents: AgentOption[];
    onAssign: (agentId: number) => void;
    onUnassign: () => void;
}

export function AssignmentPanel({
    assignedAgentId,
    agents,
    onAssign,
    onUnassign,
}: AssignmentPanelProps) {
    return (
        <div className="space-y-3">
            <h3 className="text-sm font-semibold">Assignment</h3>
            <select
                className="w-full rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 px-3 py-2 text-sm"
                value={assignedAgentId ?? ""}
                onChange={(e) => onAssign(Number(e.target.value))}
            >
                <option value="">Unassigned</option>
                {agents.map((agent) => (
                    <option key={agent.id} value={agent.id}>
                        {agent.name}
                    </option>
                ))}
            </select>
            {assignedAgentId && (
                <Button variant="secondary" onClick={onUnassign}>
                    Unassign
                </Button>
            )}
        </div>
    );
}
