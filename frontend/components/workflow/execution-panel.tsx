import React from "react";
import { WorkflowExecutionDetailResponse } from "@/types";

interface ExecutionPanelProps {
    execution?: WorkflowExecutionDetailResponse | null;
}

export function ExecutionPanel({ execution }: ExecutionPanelProps) {
    return (
        <div className="space-y-2">
            <h3 className="text-sm font-semibold">Execution</h3>
            {!execution && <p className="text-xs text-gray-500">No execution loaded.</p>}
            {execution && (
                <div className="space-y-2 text-xs">
                    <div>Status: <span className="font-semibold">{execution.status}</span></div>
                    <div>Execution ID: {execution.execution_id}</div>
                    {execution.current_node_id && <div>Current Node: {execution.current_node_id}</div>}
                    {execution.error && <div className="text-red-600">Error: {execution.error}</div>}
                </div>
            )}
        </div>
    );
}
