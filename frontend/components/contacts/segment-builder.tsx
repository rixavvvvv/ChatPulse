"use client";

import React, { useState, useCallback, useEffect } from "react";
import {
    Plus, X, ChevronDown, ChevronRight, Save, Trash2, Loader2, Users,
    Copy, Edit3, Database, Tag, Clock, Activity, ChevronDown as DropdownIcon, AlertTriangle
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export type SegmentOperator =
    | "eq" | "neq" | "contains" | "in"
    | "gt" | "gte" | "lt" | "lte"
    | "has_tag" | "attr" | "activity";

export type SegmentFieldType = "name" | "phone" | "created_at" | "last_activity" | "tags" | "attributes" | "activity";

export interface SegmentCondition {
    id: string;
    op: SegmentOperator;
    field?: string;
    value?: string | number | boolean | null;
    values?: string[];
    tag?: string;
    key?: string;
    cmp?: string;
    activityType?: string;
    activityDays?: number;
}

export interface SegmentGroup {
    id: string;
    op: "and" | "or";
    children: (SegmentGroup | SegmentCondition)[];
}

export type SegmentNode = SegmentGroup | SegmentCondition;

interface SegmentBuilderProps {
    definition?: SegmentNode;
    onChange?: (definition: SegmentNode) => void;
    onPreview?: (definition: SegmentNode) => Promise<number>;
    availableTags?: { id: number; name: string; color: string }[];
    availableAttributes?: { id: number; key: string; label: string; type: string }[];
    availableActivityTypes?: string[];
    onSave?: (name: string, definition: SegmentNode) => Promise<void>;
    onUpdate?: (id: number, name: string, definition: SegmentNode) => Promise<void>;
    onDuplicate?: (id: number) => Promise<void>;
    existingSegments?: { id: number; name: string; definition: SegmentNode }[];
    editingSegmentId?: number | null;
}

const FIELD_TYPES = [
    { value: "name", label: "Name", icon: Database },
    { value: "phone", label: "Phone", icon: Database },
    { value: "created_at", label: "Created Date", icon: Clock },
    { value: "last_activity", label: "Last Activity", icon: Activity },
    { value: "tags", label: "Tags", icon: Tag },
    { value: "attributes", label: "Attributes", icon: Database },
    { value: "activity", label: "Activity", icon: Activity },
];

const OPERATORS_BY_FIELD: Record<string, { value: SegmentOperator; label: string }[]> = {
    name: [
        { value: "eq", label: "equals" },
        { value: "neq", label: "not equals" },
        { value: "contains", label: "contains" },
    ],
    phone: [
        { value: "eq", label: "equals" },
        { value: "neq", label: "not equals" },
        { value: "contains", label: "contains" },
    ],
    created_at: [
        { value: "eq", label: "is" },
        { value: "gt", label: "after" },
        { value: "gte", label: "on or after" },
        { value: "lt", label: "before" },
        { value: "lte", label: "on or before" },
    ],
    last_activity: [
        { value: "eq", label: "is" },
        { value: "gt", label: "after" },
        { value: "gte", label: "on or after" },
        { value: "lt", label: "before" },
        { value: "lte", label: "on or before" },
    ],
    tags: [
        { value: "has_tag", label: "has tag" },
    ],
    attributes: [
        { value: "attr", label: "attribute" },
    ],
    activity: [
        { value: "activity", label: "performed" },
    ],
};

const ACTIVITY_TYPES = [
    { value: "message_sent", label: "Message Sent" },
    { value: "message_received", label: "Message Received" },
    { value: "campaign_started", label: "Campaign Started" },
    { value: "campaign_completed", label: "Campaign Completed" },
    { value: "created", label: "Contact Created" },
];

function generateId(): string {
    return Math.random().toString(36).substring(2, 11);
}

function createCondition(): SegmentCondition {
    return { id: generateId(), op: "eq", field: "name" };
}

function createGroup(op: "and" | "or" = "and"): SegmentGroup {
    return { id: generateId(), op, children: [createCondition()] };
}

function isGroup(node: SegmentNode): node is SegmentGroup {
    return "op" in node && "children" in node;
}

export function SegmentBuilder({
    definition,
    onChange,
    onPreview,
    availableTags = [],
    availableAttributes = [],
    availableActivityTypes = [],
    onSave,
    onUpdate,
    existingSegments = [],
    editingSegmentId,
}: SegmentBuilderProps) {
    const [root, setRoot] = useState<SegmentNode>(definition || createGroup());
    const [previewCount, setPreviewCount] = useState<number | null>(null);
    const [isLoadingPreview, setIsLoadingPreview] = useState(false);
    const [previewError, setPreviewError] = useState<string | null>(null);
    const [saveError, setSaveError] = useState<string | null>(null);
    const [showSaveDialog, setShowSaveDialog] = useState(false);
    const [segmentName, setSegmentName] = useState("");
    const [isSaving, setIsSaving] = useState(false);
    const [expanded, setExpanded] = useState(true);

    useEffect(() => {
        if (definition) {
            setRoot(definition);
        }
    }, [definition]);

    useEffect(() => {
        if (editingSegmentId) {
            const segment = existingSegments.find(s => s.id === editingSegmentId);
            if (segment) {
                setSegmentName(segment.name);
            }
        }
    }, [editingSegmentId, existingSegments]);

    const handleChange = useCallback((newRoot: SegmentNode) => {
        setRoot(newRoot);
        onChange?.(newRoot);
        setPreviewCount(null);
    }, [onChange]);

    const handlePreview = useCallback(async () => {
        if (!onPreview) return;
        setIsLoadingPreview(true);
        setPreviewError(null);
        try {
            const count = await onPreview(root);
            setPreviewCount(count);
        } catch (err) {
            setPreviewCount(null);
            setPreviewError(err instanceof Error ? err.message : "Failed to preview segment");
        } finally {
            setIsLoadingPreview(false);
        }
    }, [root, onPreview]);

    const handleSave = useCallback(async () => {
        if (!segmentName.trim()) return;
        setIsSaving(true);
        try {
            if (editingSegmentId && onUpdate) {
                await onUpdate(editingSegmentId, segmentName.trim(), root);
            } else if (onSave) {
                await onSave(segmentName.trim(), root);
            }
            setSegmentName("");
            setShowSaveDialog(false);
        } catch (err) {
            console.error("Failed to save segment:", err);
        } finally {
            setIsSaving(false);
        }
    }, [segmentName, root, editingSegmentId, onSave, onUpdate]);

    const addCondition = useCallback((group: SegmentGroup): SegmentGroup => {
        return { ...group, children: [...group.children, createCondition()] };
    }, []);

    const removeCondition = useCallback((group: SegmentGroup, conditionId: string): SegmentGroup => {
        if (group.children.length <= 1) return group;
        return {
            ...group,
            children: group.children.filter((c) => {
                if ("id" in c) return c.id !== conditionId;
                return true;
            }),
        };
    }, []);

    const updateCondition = useCallback((group: SegmentGroup, conditionId: string, updates: Partial<SegmentCondition>): SegmentGroup => {
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

    const updateGroupOp = useCallback((group: SegmentGroup, op: "and" | "or"): SegmentGroup => {
        return { ...group, op };
    }, []);

    const addGroup = useCallback((group: SegmentGroup): SegmentGroup => {
        return { ...group, children: [...group.children, createGroup()] };
    }, []);

    const removeGroup = useCallback((group: SegmentGroup, groupId: string): SegmentGroup | null => {
        if (group.children.length <= 1 && !groupId) return null;
        const newChildren = group.children.filter((c) => {
            if (isGroup(c) && c.id === groupId) return false;
            return true;
        });
        if (newChildren.length === 0) newChildren.push(createCondition());
        return { ...group, children: newChildren };
    }, []);

    const handleClear = useCallback(() => {
        const newRoot = createGroup();
        setRoot(newRoot);
        onChange?.(newRoot);
        setPreviewCount(null);
        setPreviewError(null);
        setSaveError(null);
        setSegmentName("");
    }, [onChange]);

    const renderCondition = (
        condition: SegmentCondition,
        onUpdate: (updates: Partial<SegmentCondition>) => void
    ) => {
        const operators = OPERATORS_BY_FIELD[condition.field || "name"] || OPERATORS_BY_FIELD.name;
        const showField = condition.op !== "has_tag" && condition.op !== "attr" && condition.op !== "activity";
        const showValue = condition.op !== "has_tag" && condition.op !== "attr" && condition.op !== "activity";
        const showValues = condition.op === "in";
        const showAttrKey = condition.op === "attr";
        const showAttrCmp = condition.op === "attr";
        const showActivityType = condition.op === "activity";

        return (
            <div className="flex items-center gap-2 flex-wrap">
                <select
                    value={condition.field || "name"}
                    onChange={(e) => onUpdate({ field: e.target.value, op: OPERATORS_BY_FIELD[e.target.value]?.[0]?.value || "eq" })}
                    className="rounded-md border border-input bg-background px-3 py-1.5 text-sm min-w-[120px]"
                >
                    {FIELD_TYPES.map((f) => (
                        <option key={f.value} value={f.value}>{f.label}</option>
                    ))}
                </select>

                <select
                    value={condition.op}
                    onChange={(e) => onUpdate({ op: e.target.value as SegmentOperator })}
                    className="rounded-md border border-input bg-background px-3 py-1.5 text-sm min-w-[120px]"
                >
                    {operators.map((o) => (
                        <option key={o.value} value={o.value}>{o.label}</option>
                    ))}
                </select>

                {showAttrKey && (
                    <select
                        value={condition.key || ""}
                        onChange={(e) => onUpdate({ key: e.target.value, value: undefined })}
                        className="rounded-md border border-input bg-background px-3 py-1.5 text-sm min-w-[140px]"
                    >
                        <option value="">Select attribute</option>
                        {availableAttributes.map((attr) => (
                            <option key={attr.id} value={attr.key}>{attr.label}</option>
                        ))}
                    </select>
                )}

                {showAttrCmp && condition.key && (
                    <>
                        <select
                            value={condition.cmp || "eq"}
                            onChange={(e) => onUpdate({ cmp: e.target.value })}
                            className="rounded-md border border-input bg-background px-3 py-1.5 text-sm"
                        >
                            <option value="eq">equals</option>
                            <option value="neq">not equals</option>
                            <option value="contains">contains</option>
                            <option value="gt">greater than</option>
                            <option value="gte">greater or equal</option>
                            <option value="lt">less than</option>
                            <option value="lte">less or equal</option>
                        </select>
                        <input
                            type="text"
                            value={condition.value as string || ""}
                            onChange={(e) => onUpdate({ value: e.target.value })}
                            className="rounded-md border border-input bg-background px-3 py-1.5 text-sm flex-1 min-w-[120px]"
                            placeholder="Value"
                        />
                    </>
                )}

                {condition.op === "has_tag" && (
                    <select
                        value={condition.tag || ""}
                        onChange={(e) => onUpdate({ tag: e.target.value })}
                        className="rounded-md border border-input bg-background px-3 py-1.5 text-sm flex-1 min-w-[160px]"
                    >
                        <option value="">Select tag</option>
                        {availableTags.map((tag) => (
                            <option key={tag.id} value={tag.name}>{tag.name}</option>
                        ))}
                    </select>
                )}

                {showActivityType && (
                    <>
                        <select
                            value={condition.activityType || ""}
                            onChange={(e) => onUpdate({ activityType: e.target.value })}
                            className="rounded-md border border-input bg-background px-3 py-1.5 text-sm min-w-[140px]"
                        >
                            <option value="">Activity type</option>
                            {(availableActivityTypes.length > 0 ? availableActivityTypes : ACTIVITY_TYPES.map(a => a.value)).map((type) => (
                                <option key={type} value={type}>{type.replace(/_/g, " ").replace(/\b\w/g, l => l.toUpperCase())}</option>
                            ))}
                        </select>
                        <input
                            type="number"
                            value={condition.activityDays as number || ""}
                            onChange={(e) => onUpdate({ activityDays: parseInt(e.target.value) || undefined })}
                            className="rounded-md border border-input bg-background px-3 py-1.5 text-sm w-20"
                            placeholder="Days"
                            min={1}
                        />
                        <span className="text-sm text-muted-foreground">days ago</span>
                    </>
                )}

                {showValue && !showValues && !showAttrKey && !showActivityType && (
                    <input
                        type={condition.field === "created_at" || condition.field === "last_activity" ? "date" : "text"}
                        value={condition.value as string || ""}
                        onChange={(e) => onUpdate({ value: e.target.value })}
                        className="rounded-md border border-input bg-background px-3 py-1.5 text-sm flex-1 min-w-[120px]"
                        placeholder="Value"
                    />
                )}

                {showValues && (
                    <input
                        value={(condition.values || []).join(", ")}
                        onChange={(e) => onUpdate({ values: e.target.value.split(",").map((v) => v.trim()).filter(Boolean) })}
                        className="rounded-md border border-input bg-background px-3 py-1.5 text-sm flex-1 min-w-[200px]"
                        placeholder="Comma separated values"
                    />
                )}
            </div>
        );
    };

    const renderGroup = (
        group: SegmentGroup,
        onUpdate: (g: SegmentGroup) => void,
        depth = 0,
        isRoot = false
    ): React.ReactNode => {
        return (
            <div
                key={group.id}
                className={cn("space-y-2", depth > 0 && "ml-6 border-l-2 border-muted pl-4")}
            >
                <div className="flex items-center gap-2">
                    {depth > 0 && (
                        <select
                            value={group.op}
                            onChange={(e) => onUpdate(updateGroupOp(group, e.target.value as "and" | "or"))}
                            className="rounded-md border border-input bg-background px-3 py-1.5 text-sm font-semibold min-w-[80px]"
                        >
                            <option value="and">AND</option>
                            <option value="or">OR</option>
                        </select>
                    )}
                    {depth === 0 && !isRoot && (
                        <Badge variant="outline" className="font-normal">
                            {group.op.toUpperCase()}
                        </Badge>
                    )}
                    {depth === 0 && (
                        <span className="text-xs text-muted-foreground">
                            {group.children.length} rule{group.children.length !== 1 ? "s" : ""}
                        </span>
                    )}
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
                                <div key={child.id} className="relative group/rule">
                                    <div className="flex items-start gap-2 p-3 bg-muted/30 rounded-lg border border-transparent hover:border-muted-foreground/20 transition-colors">
                                        <div className="flex-1">
                                            {renderCondition(child, (updates) => {
                                                const newChildren = [...group.children];
                                                newChildren[idx] = { ...child, ...updates } as SegmentCondition;
                                                onUpdate({ ...group, children: newChildren });
                                            })}
                                        </div>
                                        {group.children.length > 1 && (
                                            <button
                                                onClick={() => onUpdate(removeCondition(group, child.id))}
                                                className="p-1.5 text-muted-foreground hover:text-destructive opacity-0 group-hover/rule:opacity-100 transition-opacity"
                                                title="Remove rule"
                                            >
                                                <X className="h-4 w-4" />
                                            </button>
                                        )}
                                    </div>
                                </div>
                            );
                        }
                    })}
                </div>

                <div className="flex items-center gap-3 pt-1">
                    <button
                        onClick={() => onUpdate(addCondition(group))}
                        className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground px-2 py-1 rounded hover:bg-muted"
                    >
                        <Plus className="h-3 w-3" /> Add rule
                    </button>
                    <button
                        onClick={() => onUpdate(addGroup(group))}
                        className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground px-2 py-1 rounded hover:bg-muted"
                    >
                        <Plus className="h-3 w-3" /> Add group
                    </button>
                </div>
            </div>
        );
    };

    const handleRootUpdate = (updatedGroup: SegmentGroup) => {
        handleChange(updatedGroup);
    };

    return (
        <div className="space-y-4">
            <div className="flex items-center justify-between">
                <button
                    onClick={() => setExpanded(!expanded)}
                    className="flex items-center gap-2 text-sm font-medium hover:text-foreground"
                >
                    {expanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                    <Database className="h-4 w-4" />
                    Segment Builder
                </button>
                <div className="flex items-center gap-2">
                    <Button
                        size="sm"
                        variant="outline"
                        onClick={() => setShowSaveDialog(true)}
                    >
                        <Save className="h-4 w-4 mr-1" />
                        {editingSegmentId ? "Update" : "Save"}
                    </Button>
                    <Button size="sm" variant="ghost" onClick={handleClear}>
                        Clear
                    </Button>
                </div>
            </div>

            {expanded && isGroup(root) && (
                <div className="space-y-4">
                    {renderGroup(root, handleRootUpdate, 0, true)}

                    <div className="flex items-center justify-between pt-4 border-t">
                        <div className="flex items-center gap-2">
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
                                Preview Audience
                            </Button>
                            {previewError && (
                                <Button
                                    size="sm"
                                    variant="ghost"
                                    onClick={handlePreview}
                                    className="text-red-500"
                                >
                                    Retry
                                </Button>
                            )}
                        </div>
                        {previewCount !== null && (
                            <Badge variant="secondary" className="text-sm px-3 py-1">
                                {previewCount.toLocaleString()} contact{previewCount !== 1 ? "s" : ""}
                            </Badge>
                        )}
                    </div>

                    {previewError && (
                        <div className="flex items-center gap-2 text-sm text-red-500 bg-red-50 dark:bg-red-900/20 p-2 rounded">
                            <AlertTriangle className="h-4 w-4" />
                            {previewError}
                        </div>
                    )}
                </div>
            )}

            {showSaveDialog && (
                <Card>
                    <CardContent className="pt-4">
                        <div className="flex items-center gap-2">
                            <Input
                                value={segmentName}
                                onChange={(e) => setSegmentName(e.target.value)}
                                placeholder="Segment name"
                                className="flex-1"
                                onKeyDown={(e) => e.key === "Enter" && handleSave()}
                            />
                            <Button
                                onClick={handleSave}
                                disabled={!segmentName.trim() || isSaving}
                            >
                                {isSaving ? (
                                    <Loader2 className="h-4 w-4 animate-spin" />
                                ) : editingSegmentId ? (
                                    "Update"
                                ) : (
                                    "Save"
                                )}
                            </Button>
                            <Button size="sm" variant="ghost" onClick={() => setShowSaveDialog(false)}>
                                <X className="h-4 w-4" />
                            </Button>
                        </div>
                    </CardContent>
                </Card>
            )}
        </div>
    );
}

// Segment List Component
interface SegmentListProps {
    segments: { id: number; name: string; approx_size: number; status: string; created_at: string }[];
    isLoading?: boolean;
    onEdit?: (id: number) => void;
    onDuplicate?: (id: number) => void;
    onDelete?: (id: number) => void;
    onSelect?: (id: number) => void;
}

export function SegmentList({
    segments,
    isLoading,
    onEdit,
    onDuplicate,
    onDelete,
    onSelect,
}: SegmentListProps) {
    if (isLoading) {
        return (
            <div className="space-y-2">
                {[1, 2, 3].map((i) => (
                    <div key={i} className="animate-pulse rounded-lg border p-4">
                        <div className="h-4 w-32 rounded bg-muted" />
                    </div>
                ))}
            </div>
        );
    }

    if (segments.length === 0) {
        return (
            <div className="text-center py-8 text-muted-foreground">
                <Database className="h-8 w-8 mx-auto mb-2 opacity-50" />
                <p>No segments yet</p>
                <p className="text-sm">Create a segment to organize your contacts</p>
            </div>
        );
    }

    return (
        <div className="space-y-2">
            {segments.map((segment) => (
                <div
                    key={segment.id}
                    className="flex items-center justify-between rounded-lg border p-4 hover:bg-muted/30 transition-colors group"
                >
                    <button
                        onClick={() => onSelect?.(segment.id)}
                        className="flex-1 text-left"
                    >
                        <div className="flex items-center gap-2">
                            <Database className="h-4 w-4 text-muted-foreground" />
                            <span className="font-medium">{segment.name}</span>
                        </div>
                        <div className="mt-1 flex items-center gap-3 text-xs text-muted-foreground">
                            <span className="flex items-center gap-1">
                                <Users className="h-3 w-3" />
                                {segment.approx_size.toLocaleString()} contacts
                            </span>
                            <Badge
                                variant={segment.status === "active" ? "secondary" : "outline"}
                                className="text-xs"
                            >
                                {segment.status}
                            </Badge>
                        </div>
                    </button>
                    <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                        <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => onEdit?.(segment.id)}
                            title="Edit"
                        >
                            <Edit3 className="h-4 w-4" />
                        </Button>
                        <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => onDuplicate?.(segment.id)}
                            title="Duplicate"
                        >
                            <Copy className="h-4 w-4" />
                        </Button>
                        <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => onDelete?.(segment.id)}
                            title="Delete"
                            className="hover:text-destructive"
                        >
                            <Trash2 className="h-4 w-4" />
                        </Button>
                    </div>
                </div>
            ))}
        </div>
    );
}

export type { SegmentCondition, SegmentGroup, SegmentNode };