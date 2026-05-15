import React from "react";
import { Button } from "@/components/ui/button";

interface WorkflowToolbarProps {
    name: string;
    description: string;
    isSaving: boolean;
    lastSavedAt?: string | null;
    onRun: () => void;
}

export function WorkflowToolbar({ name, description, isSaving, lastSavedAt, onRun }: WorkflowToolbarProps) {
    return (
        <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
                <h2 className="text-lg font-semibold">{name}</h2>
                <p className="text-xs text-gray-500">{description || "No description"}</p>
            </div>
            <div className="flex items-center gap-3 text-xs text-gray-500">
                <span>{isSaving ? "Saving..." : lastSavedAt ? `Saved ${new Date(lastSavedAt).toLocaleTimeString()}` : "Not saved"}</span>
                <Button onClick={onRun}>Run Test</Button>
            </div>
        </div>
    );
}
