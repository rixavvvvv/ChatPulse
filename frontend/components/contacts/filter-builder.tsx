"use client";

import React, { useState, useCallback, useMemo, useEffect } from "react";
import { Plus, X, Filter, ChevronDown, ChevronRight, Save, Trash2, Loader2, Users } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";

export type FilterOperator =
    | "eq" | "neq" | "contains" | "in"
    | "gt" | "gte" | "lt" | "lte"
    | "has_tag" | "attr";

export type FilterField = "name" | "phone" | "created_at" | "tags" | "attributes";

export interface FilterCondition {
    id: string;
    op: FilterOperator;
    field?: string;
    value?: string | number | boolean | null;
    values?: string[];
    tag?: string;
    key?: string;
    cmp?: string;
}

export interface FilterGroup {
    id: string;
    op: "and" | "or";
    children: (FilterGroup | FilterCondition)[];
}

export type FilterNode = FilterGroup | FilterCondition;

export interface SavedFilter {
    id: number;
    name: string;
    definition: FilterNode;
    created_at: string;
}

interface FilterBuilderProps {
    definition?: FilterNode;
    onChange?: (definition: FilterNode) => void;
    onPreview?: (definition: FilterNode) => Promise<number>;
    availableTags?: { id: number; name: string; color: string }[];
    availableAttributes?: { id: number; key: string; label: string; type: string }[];
    savedFilters?: SavedFilter[];
    onSaveFilter?: (name: string, definition: FilterNode) => void;
    onDeleteFilter?: (id: number) => void;
    onLoadFilter?: (definition: FilterNode) => void;
}

const OPERATORS: { value: FilterOperator; label: string; fields: FilterField[] }[] = [
    { value: "eq", label: "equals", fields: ["name", "phone", "created_at"] },
    { value: "neq", label: "not equals", fields: ["name", "phone", "created_at"] },
    { value: "contains", label: "contains", fields: ["name", "phone"] },
    { value: "in", label: "is in", fields: ["name", "phone"] },
    { value: "gt", label: "greater than", fields: ["created_at"] },
    { value: "gte", label: "greater or equal", fields: ["created_at"] },
    { value: "lt", label: "less than", fields: ["created_at"] },
    { value: "lte", label: "less or equal", fields: ["created_at"] },
    { value: "has_tag", label: "has tag", fields: ["tags"] },
    { value: "attr", label: "attribute", fields: ["attributes"] },
];

const FIELD_OPTIONS = [
    { value: "name", label: "Name" },
    { value: "phone", label: "Phone" },
    { value: "created_at", label: "Created Date" },
    { value: "tags", label: "Tags" },
    { value: "attributes", label: "Attributes" },
];

function generateId(): string {
    return Math.random().toString(36).substring(2, 11);
}

function createCondition(): FilterCondition {
    return { id: generateId(), op: "eq", field: "name" };
}

function createGroup(op: "and" | "or" = "and"): FilterGroup {
    return { id: generateId(), op, children: [createCondition()] };
}

export function FilterBuilder({
    definition,
    onChange,
    onPreview,
    availableTags = [],
    availableAttributes = [],
    savedFilters = [],
    onSaveFilter,
    onDeleteFilter,
    onLoadFilter,
}: FilterBuilderProps) {
    const [root, setRoot] = useState<FilterNode>(definition || createGroup());
    const [previewCount, setPreviewCount] = useState<number | null>(null);
    const [isLoadingPreview, setIsLoadingPreview] = useState(false);
    const [showSaveDialog, setShowSaveDialog] = useState(false);
    const [filterName, setFilterName] = useState("");
    const [expanded, setExpanded] = useState(true);

    useEffect(() => {
        if (definition) {
            setRoot(definition);
        }
    }, [definition]);

    const handleChange = useCallback((newRoot: FilterNode) => {
        setRoot(newRoot);
        onChange?.(newRoot);
    }, [onChange]);

    const handlePreview = useCallback(async () => {
        if (!onPreview) return;
        setIsLoadingPreview(true);
        try {
            const count = await onPreview(root);
            setPreviewCount(count);
        } catch {
            setPreviewCount(null);
        } finally {
            setIsLoadingPreview(false);
        }
    }, [root, onPreview]);

    const handleSave = useCallback(() => {
        if (filterName.trim() && onSaveFilter) {
            onSaveFilter(filterName.trim(), root);
            setFilterName("");
            setShowSaveDialog(false);
        }
    }, [filterName, root, onSaveFilter]);

    const addCondition = useCallback((group: FilterGroup) => {
        return {
            ...group,
            children: [...group.children, createCondition()],
        };
    }, []);

    const removeCondition = useCallback((group: FilterGroup, conditionId: string) => {
        if (group.children.length <= 1) return group;
        return {
            ...group,
            children: group.children.filter((c) => {
                if ("id" in c) return c.id !== conditionId;
                return true;
            }),
        };
    }, []);

    const updateCondition = useCallback((group: FilterGroup, conditionId: string, updates: Partial<FilterCondition>) => {
        return {
            ...group,
            children: group.children.map((c) => {
                if ("id" in c && c.id === conditionId) {
                    return { ...c, ...updates };
                }
                return c;
            }),
        };
    }, []);

    const updateGroupOp = useCallback((group: FilterGroup, op: "and" | "or") => {
        return { ...group, op };
    }, []);

    const addGroup = useCallback((group: FilterGroup) => {
        return {
            ...group,
            children: [...group.children, createGroup()],
        };
    }, []);

    const isGroup = (node: FilterNode): node is FilterGroup => "op" in node && "children" in node;

    const renderCondition = (condition: FilterCondition, onUpdate: (updates: Partial<FilterCondition>) => void) => {
        const currentOp = OPERATORS.find((o) => o.value === condition.op);
        const showField = condition.op !== "has_tag" && condition.op !== "attr";
        const showValue = condition.op !== "has_tag";
        const showValues = condition.op === "in";
        const showAttrKey = condition.op === "attr";
        const showAttrCmp = condition.op === "attr";

        return (
            <div className="flex items-center gap-2 p-2 bg-muted/30 rounded-md">
                <select
                    value={condition.field || "name"}
                    onChange={(e) => onUpdate({ field: e.target.value })}
                    className="rounded-md border border-input bg-background px-2 py-1 text-sm"
                >
                    {FIELD_OPTIONS.filter((f) => currentOp?.fields.includes(f.value as FilterField)).map((f) => (
                        <option key={f.value} value={f.value}>{f.label}</option>
                    ))}
                </select>

                <select
                    value={condition.op}
                    onChange={(e) => onUpdate({ op: e.target.value as FilterOperator })}
                    className="rounded-md border border-input bg-background px-2 py-1 text-sm"
                >
                    {OPERATORS.filter((o) => o.fields.includes((condition.field as FilterField) || "name")).map((o) => (
                        <option key={o.value} value={o.value}>{o.label}</option>
                    ))}
                </select>

                {showAttrKey && (
                    <select
                        value={condition.key || ""}
                        onChange={(e) => onUpdate({ key: e.target.value })}
                        className="rounded-md border border-input bg-background px-2 py-1 text-sm"
                    >
                        <option value="">Select attribute</option>
                        {availableAttributes.map((attr) => (
                            <option key={attr.id} value={attr.key}>{attr.label}</option>
                        ))}
                    </select>
                )}

                {showAttrCmp && condition.key && (
                    <select
                        value={condition.cmp || "eq"}
                        onChange={(e) => onUpdate({ cmp: e.target.value })}
                        className="rounded-md border border-input bg-background px-2 py-1 text-sm"
                    >
                        <option value="eq">equals</option>
                        <option value="neq">not equals</option>
                        <option value="contains">contains</option>
                        <option value="gt">greater than</option>
                        <option value="gte">greater or equal</option>
                        <option value="lt">less than</option>
                        <option value="lte">less or equal</option>
                    </select>
                )}

                {condition.op === "has_tag" && (
                    <select
                        value={condition.tag || ""}
                        onChange={(e) => onUpdate({ tag: e.target.value })}
                        className="rounded-md border border-input bg-background px-2 py-1 text-sm flex-1"
                    >
                        <option value="">Select tag</option>
                        {availableTags.map((tag) => (
                            <option key={tag.id} value={tag.name}>{tag.name}</option>
                        ))}
                    </select>
                )}

                {showValue && !showValues && !showAttrKey && (
                    <input
                        type={condition.field === "created_at" ? "datetime-local" : "text"}
                        value={condition.value as string || ""}
                        onChange={(e) => onUpdate({ value: e.target.value })}
                        className="rounded-md border border-input bg-background px-2 py-1 text-sm flex-1"
                        placeholder="Value"
                    />
                )}

                {showValues && (
                    <input
                        value={(condition.values || []).join(", ")}
                        onChange={(e) => onUpdate({ values: e.target.value.split(",").map((v) => v.trim()).filter(Boolean) })}
                        className="rounded-md border border-input bg-background px-2 py-1 text-sm flex-1"
                        placeholder="Comma separated values"
                    />
                )}

                {showValue && condition.key && condition.op !== "attr" && (
                    <input
                        type="text"
                        value={condition.value as string || ""}
                        onChange={(e) => onUpdate({ value: e.target.value })}
                        className="rounded-md border border-input bg-background px-2 py-1 text-sm flex-1"
                        placeholder="Value"
                    />
                )}
            </div>
        );
    };

    const renderGroup = (group: FilterGroup, onUpdate: (g: FilterGroup) => void, depth = 0): React.ReactNode => {
        return (
            <div
                key={group.id}
                className={cn("space-y-2", depth > 0 && "ml-4 border-l-2 border-muted pl-3")}
            >
                <div className="flex items-center gap-2">
                    <select
                        value={group.op}
                        onChange={(e) => onUpdate(updateGroupOp(group, e.target.value as "and" | "or"))}
                        className="rounded-md border border-input bg-background px-2 py-1 text-sm font-medium"
                    >
                        <option value="and">AND</option>
                        <option value="or">OR</option>
                    </select>
                    <span className="text-xs text-muted-foreground">
                        {group.children.length} condition{group.children.length !== 1 ? "s" : ""}
                    </span>
                </div>

                <div className="space-y-2">
                    {group.children.map((child, idx) => {
                        if (isGroup(child)) {
                            return renderGroup(child, (updated) => {
                                const newChildren = [...group.children];
                                newChildren[idx] = updated;
                                onUpdate({ ...group, children: newChildren });
                            }, depth + 1);
                        } else {
                            return (
                                <div key={child.id} className="relative group/condition">
                                    {renderCondition(child, (updates) => {
                                        const newChildren = [...group.children];
                                        newChildren[idx] = { ...child, ...updates } as FilterCondition;
                                        onUpdate({ ...group, children: newChildren });
                                    })}
                                    {group.children.length > 1 && (
                                        <button
                                            onClick={() => onUpdate(removeCondition(group, child.id))}
                                            className="absolute -right-1 -top-1 opacity-0 group-hover/condition:opacity-100 p-1 text-muted-foreground hover:text-destructive"
                                        >
                                            <X className="h-3 w-3" />
                                        </button>
                                    )}
                                </div>
                            );
                        }
                    })}
                </div>

                <div className="flex gap-2">
                    <button
                        onClick={() => onUpdate(addCondition(group))}
                        className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
                    >
                        <Plus className="h-3 w-3" /> Add condition
                    </button>
                    <button
                        onClick={() => onUpdate(addGroup(group))}
                        className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
                    >
                        <Plus className="h-3 w-3" /> Add group
                    </button>
                </div>
            </div>
        );
    };

    const handleRootUpdate = (updatedGroup: FilterGroup) => {
        handleChange(updatedGroup);
    };

    const handleClear = () => {
        const newRoot = createGroup();
        setRoot(newRoot);
        onChange?.(newRoot);
        setPreviewCount(null);
    };

    return (
        <div className="space-y-4">
            <div className="flex items-center justify-between">
                <button
                    onClick={() => setExpanded(!expanded)}
                    className="flex items-center gap-2 text-sm font-medium"
                >
                    {expanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                    <Filter className="h-4 w-4" />
                    Filter
                </button>
                <div className="flex items-center gap-2">
                    {savedFilters.length > 0 && (
                        <select
                            onChange={(e) => {
                                const saved = savedFilters.find((f) => f.id === Number(e.target.value));
                                if (saved && onLoadFilter) {
                                    onLoadFilter(saved.definition);
                                    setRoot(saved.definition);
                                }
                            }}
                            className="rounded-md border border-input bg-background px-2 py-1 text-sm"
                        >
                            <option value="">Load filter...</option>
                            {savedFilters.map((f) => (
                                <option key={f.id} value={f.id}>{f.name}</option>
                            ))}
                        </select>
                    )}
                    <Button size="sm" variant="outline" onClick={() => setShowSaveDialog(true)}>
                        <Save className="h-4 w-4 mr-1" />
                        Save
                    </Button>
                    <Button size="sm" variant="outline" onClick={handleClear}>
                        Clear
                    </Button>
                </div>
            </div>

            {expanded && isGroup(root) && (
                <div className="space-y-4">
                    {renderGroup(root, handleRootUpdate)}

                    <div className="flex items-center justify-between pt-2 border-t">
                        <Button
                            size="sm"
                            variant="outline"
                            onClick={handlePreview}
                            disabled={isLoadingPreview}
                        >
                            {isLoadingPreview ? (
                                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                            ) : (
                                <Users className="h-4 w-4 mr-2" />
                            )}
                            Preview
                        </Button>
                        {previewCount !== null && (
                            <Badge variant="secondary">
                                {previewCount} contact{previewCount !== 1 ? "s" : ""}
                            </Badge>
                        )}
                    </div>
                </div>
            )}

            {showSaveDialog && (
                <div className="flex items-center gap-2 p-3 bg-muted/50 rounded-lg">
                    <Input
                        value={filterName}
                        onChange={(e) => setFilterName(e.target.value)}
                        placeholder="Filter name"
                        className="flex-1"
                        onKeyDown={(e) => e.key === "Enter" && handleSave()}
                    />
                    <Button size="sm" onClick={handleSave} disabled={!filterName.trim()}>
                        Save
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => setShowSaveDialog(false)}>
                        <X className="h-4 w-4" />
                    </Button>
                </div>
            )}
        </div>
    );
}