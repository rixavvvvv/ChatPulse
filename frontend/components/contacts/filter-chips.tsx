"use client";

import React from "react";
import { X, Tag, User, Phone, Calendar, FileText } from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import type { FilterNode, FilterCondition, FilterGroup } from "./filter-builder";

interface FilterChipsProps {
    definition: FilterNode;
    onRemove?: (conditionId: string) => void;
    onClear?: () => void;
    availableTags?: { id: number; name: string; color: string }[];
    availableAttributes?: { id: number; key: string; label: string; type: string }[];
}

const fieldIcons: Record<string, React.ComponentType<{ className?: string }>> = {
    name: User,
    phone: Phone,
    created_at: Calendar,
    tags: Tag,
    attributes: FileText,
};

const operatorLabels: Record<string, string> = {
    eq: "=",
    neq: "≠",
    contains: "contains",
    in: "in",
    gt: ">",
    gte: "≥",
    lt: "<",
    lte: "≤",
    has_tag: "has tag",
    attr: "attribute",
};

function isGroup(node: FilterNode): node is FilterGroup {
    return "op" in node && "children" in node;
}

function isCondition(node: FilterNode): node is FilterCondition {
    return "id" in node && "op" in node;
}

function getConditionLabel(
    condition: FilterCondition,
    availableTags: { id: number; name: string; color: string }[],
    availableAttributes: { id: number; key: string; label: string; type: string }[]
): string {
    const field = condition.field || "name";
    const op = condition.op;
    const Icon = fieldIcons[field] || User;

    if (op === "has_tag") {
        return `has tag: ${condition.tag || "any"}`;
    }

    if (op === "attr") {
        const attr = availableAttributes.find((a) => a.key === condition.key);
        return `${attr?.label || condition.key} ${operatorLabels[condition.cmp || "eq"] || "="} ${condition.value}`;
    }

    const value = condition.values ? condition.values.join(", ") : condition.value;
    return `${field} ${operatorLabels[op] || "="} ${value}`;
}

function extractConditions(group: FilterGroup): FilterCondition[] {
    const conditions: FilterCondition[] = [];

    for (const child of group.children) {
        if (isCondition(child)) {
            conditions.push(child);
        } else if (isGroup(child)) {
            conditions.push(...extractConditions(child));
        }
    }

    return conditions;
}

export function FilterChips({
    definition,
    onRemove,
    onClear,
    availableTags = [],
    availableAttributes = [],
}: FilterChipsProps) {
    if (!isGroup(definition)) {
        return null;
    }

    const conditions = extractConditions(definition);

    if (conditions.length === 0) {
        return null;
    }

    return (
        <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm text-muted-foreground">Active filters:</span>

            {conditions.map((condition) => {
                const label = getConditionLabel(condition, availableTags, availableAttributes);
                const Icon = fieldIcons[condition.field || "name"] || User;

                return (
                    <Badge
                        key={condition.id}
                        variant="secondary"
                        className="flex items-center gap-1.5 pr-1"
                    >
                        <Icon className="h-3 w-3" />
                        <span className="text-xs">{label}</span>
                        {onRemove && (
                            <button
                                onClick={() => onRemove(condition.id)}
                                className="ml-1 p-0.5 hover:bg-muted rounded"
                            >
                                <X className="h-3 w-3" />
                            </button>
                        )}
                    </Badge>
                );
            })}

            {onClear && (
                <button
                    onClick={onClear}
                    className="text-xs text-muted-foreground hover:text-foreground underline"
                >
                    Clear all
                </button>
            )}
        </div>
    );
}

export function useFilterChips(
    definition: FilterNode | undefined,
    availableTags: { id: number; name: string; color: string }[] = [],
    availableAttributes: { id: number; key: string; label: string; type: string }[] = []
) {
    if (!definition || !isGroup(definition)) {
        return null;
    }

    const conditions = extractConditions(definition);

    return conditions.map((condition) => ({
        id: condition.id,
        label: getConditionLabel(condition, availableTags, availableAttributes),
        icon: fieldIcons[condition.field || "name"] || User,
    }));
}