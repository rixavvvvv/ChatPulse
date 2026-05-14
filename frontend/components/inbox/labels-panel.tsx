import React from "react";
import { ConversationLabel } from "@/types";
import { cn } from "@/lib/utils";

interface LabelsPanelProps {
    labels: ConversationLabel[];
    assigned: ConversationLabel[];
    onAssign: (labelId: number) => void;
    onRemove: (labelId: number) => void;
}

export function LabelsPanel({ labels, assigned, onAssign, onRemove }: LabelsPanelProps) {
    const assignedMap = new Map(assigned.map((item) => [item.id, item]));

    return (
        <div className="space-y-3">
            <h3 className="text-sm font-semibold">Labels</h3>
            <div className="flex flex-wrap gap-2">
                {labels.map((label) => {
                    const assignment = assignedMap.get(label.id);
                    return (
                        <button
                            key={label.id}
                            onClick={() =>
                                assignment ? onRemove(label.id) : onAssign(label.id)
                            }
                            className={cn(
                                "px-3 py-1 rounded-full text-xs border transition-colors",
                                assignment
                                    ? "border-transparent text-white"
                                    : "border-gray-300 dark:border-gray-700 text-gray-700 dark:text-gray-300"
                            )}
                            style={{
                                backgroundColor: assignment ? label.color : "transparent",
                            }}
                        >
                            {label.name}
                        </button>
                    );
                })}
                {labels.length === 0 && (
                    <p className="text-sm text-gray-500">No labels</p>
                )}
            </div>
        </div>
    );
}
