import React from "react";
import { WorkflowValidationError } from "@/types";

interface ValidationPanelProps {
    errors: WorkflowValidationError[];
}

export function ValidationPanel({ errors }: ValidationPanelProps) {
    return (
        <div className="space-y-2">
            <h3 className="text-sm font-semibold">Validation</h3>
            {errors.length === 0 && (
                <p className="text-xs text-emerald-600">No validation issues.</p>
            )}
            {errors.map((error, index) => (
                <div key={`${error.error_type}-${index}`} className="text-xs text-red-600">
                    {error.message}
                </div>
            ))}
        </div>
    );
}
