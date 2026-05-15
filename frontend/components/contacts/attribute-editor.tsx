"use client";

import React, { useState, useEffect } from "react";
import { Edit2, Plus, X, Save, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

interface ContactAttribute {
    key: string;
    label: string;
    value: string | number | boolean | null;
    type: "text" | "number" | "boolean" | "date";
}

interface AttributeDefinition {
    key: string;
    label: string;
    type: "text" | "number" | "boolean" | "date";
    is_indexed?: boolean;
}

interface AttributeEditorProps {
    attributes: ContactAttribute[];
    definitions?: AttributeDefinition[];
    onUpdate?: (key: string, value: string | number | boolean | null) => void;
    onCreate?: (key: string, value: string | number | boolean | null) => void;
    isLoading?: boolean;
    editable?: boolean;
}

function AttributeValueInput({
    attribute,
    value,
    onChange,
    onCancel,
    onSave,
    isSaving = false,
}: {
    attribute: ContactAttribute;
    value: string;
    onChange: (value: string) => void;
    onCancel: () => void;
    onSave: () => void;
    isSaving?: boolean;
}) {
    const [inputValue, setInputValue] = useState(value);

    useEffect(() => {
        setInputValue(value);
    }, [value]);

    const handleSave = () => {
        let parsedValue: string | number | boolean | null = inputValue;

        if (attribute.type === "number") {
            parsedValue = inputValue === "" ? null : Number(inputValue);
        } else if (attribute.type === "boolean") {
            parsedValue = inputValue === "true";
        }

        onChange(parsedValue as string | number | boolean | null);
        onSave();
    };

    return (
        <div className="flex items-center gap-2">
            {attribute.type === "boolean" ? (
                <select
                    value={inputValue}
                    onChange={(e) => setInputValue(e.target.value)}
                    className="rounded-md border border-input bg-background px-2 py-1 text-sm"
                >
                    <option value="true">True</option>
                    <option value="false">False</option>
                </select>
            ) : (
                <input
                    type={attribute.type === "date" ? "date" : attribute.type === "number" ? "number" : "text"}
                    value={inputValue}
                    onChange={(e) => setInputValue(e.target.value)}
                    className="rounded-md border border-input bg-background px-2 py-1 text-sm flex-1"
                />
            )}
            <button
                onClick={handleSave}
                disabled={isSaving}
                className="p-1 text-green-600 hover:text-green-700"
            >
                {isSaving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
            </button>
            <button
                onClick={onCancel}
                className="p-1 text-muted-foreground hover:text-foreground"
            >
                <X className="h-4 w-4" />
            </button>
        </div>
    );
}

function AttributeRow({
    attribute,
    onEdit,
    onDelete,
    editable = true,
}: {
    attribute: ContactAttribute;
    onEdit?: () => void;
    onDelete?: () => void;
    editable?: boolean;
}) {
    const [isEditing, setIsEditing] = useState(false);
    const [editValue, setEditValue] = useState<string>("");

    const displayValue = () => {
        if (attribute.value === null || attribute.value === undefined) {
            return <span className="text-muted-foreground">Not set</span>;
        }
        if (typeof attribute.value === "boolean") {
            return attribute.value ? (
                <span className="text-green-600">Yes</span>
            ) : (
                <span className="text-muted-foreground">No</span>
            );
        }
        return String(attribute.value);
    };

    if (isEditing) {
        return (
            <AttributeValueInput
                attribute={attribute}
                value={editValue}
                onChange={(val) => setEditValue(String(val ?? ""))}
                onCancel={() => setIsEditing(false)}
                onSave={() => setIsEditing(false)}
            />
        );
    }

    return (
        <div className="flex items-center justify-between py-2">
            <div className="flex-1 min-w-0">
                <span className="text-sm font-medium">{attribute.label}</span>
                <div className="text-sm text-muted-foreground">{displayValue()}</div>
            </div>
            {editable && (
                <div className="flex items-center gap-1">
                    <button
                        onClick={() => {
                            setEditValue(String(attribute.value ?? ""));
                            setIsEditing(true);
                        }}
                        className="p-1 text-muted-foreground hover:text-foreground"
                    >
                        <Edit2 className="h-4 w-4" />
                    </button>
                    {onDelete && (
                        <button
                            onClick={onDelete}
                            className="p-1 text-muted-foreground hover:text-red-600"
                        >
                            <X className="h-4 w-4" />
                        </button>
                    )}
                </div>
            )}
        </div>
    );
}

export function AttributeEditor({
    attributes = [],
    definitions = [],
    onUpdate,
    onCreate,
    isLoading = false,
    editable = true,
}: AttributeEditorProps) {
    const [showAddForm, setShowAddForm] = useState(false);
    const [newKey, setNewKey] = useState("");
    const [newValue, setNewValue] = useState("");
    const [newType, setNewType] = useState<"text" | "number" | "boolean" | "date">("text");

    const availableDefinitions = definitions.filter(
        (def) => !attributes.some((attr) => attr.key === def.key)
    );

    const handleAddFromDefinition = (key: string) => {
        if (onCreate) {
            onCreate(key, null);
        }
    };

    const handleCreateCustom = () => {
        if (!newKey.trim() || !onCreate) return;

        let parsedValue: string | number | boolean | null = newValue;
        if (newType === "number") {
            parsedValue = newValue === "" ? null : Number(newValue);
        } else if (newType === "boolean") {
            parsedValue = newValue === "true";
        }

        onCreate(newKey.trim(), parsedValue);
        setNewKey("");
        setNewValue("");
        setShowAddForm(false);
    };

    if (isLoading) {
        return (
            <div className="space-y-2">
                {Array.from({ length: 3 }).map((_, i) => (
                    <div key={i} className="flex items-center justify-between py-2">
                        <div className="space-y-1">
                            <div className="h-4 w-24 bg-muted animate-pulse rounded" />
                            <div className="h-3 w-32 bg-muted animate-pulse rounded" />
                        </div>
                    </div>
                ))}
            </div>
        );
    }

    return (
        <div className="space-y-3">
            {attributes.length === 0 && !showAddForm ? (
                <p className="text-sm text-muted-foreground">No attributes yet</p>
            ) : (
                <div className="divide-y">
                    {attributes.map((attr) => (
                        <AttributeRow
                            key={attr.key}
                            attribute={attr}
                            editable={editable}
                        />
                    ))}
                </div>
            )}

            {editable && (
                <div className="space-y-2">
                    {availableDefinitions.length > 0 && !showAddForm && (
                        <div className="flex flex-wrap gap-2">
                            <span className="text-xs text-muted-foreground">Add existing:</span>
                            {availableDefinitions.map((def) => (
                                <button
                                    key={def.key}
                                    onClick={() => handleAddFromDefinition(def.key)}
                                    className="inline-flex items-center px-2 py-1 text-xs bg-muted hover:bg-muted/80 rounded-md transition-colors"
                                >
                                    <Plus className="h-3 w-3 mr-1" />
                                    {def.label}
                                </button>
                            ))}
                        </div>
                    )}

                    {!showAddForm && (
                        <button
                            onClick={() => setShowAddForm(true)}
                            className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
                        >
                            <Plus className="h-4 w-4" />
                            Add custom attribute
                        </button>
                    )}

                    {showAddForm && (
                        <div className="p-3 bg-muted/50 rounded-lg space-y-3">
                            <div className="flex gap-2">
                                <input
                                    type="text"
                                    value={newKey}
                                    onChange={(e) => setNewKey(e.target.value)}
                                    placeholder="Attribute name"
                                    className="flex-1 rounded-md border border-input bg-background px-3 py-1.5 text-sm"
                                />
                                <select
                                    value={newType}
                                    onChange={(e) => setNewType(e.target.value as typeof newType)}
                                    className="rounded-md border border-input bg-background px-2 py-1.5 text-sm"
                                >
                                    <option value="text">Text</option>
                                    <option value="number">Number</option>
                                    <option value="boolean">Boolean</option>
                                    <option value="date">Date</option>
                                </select>
                            </div>
                            <div className="flex gap-2">
                                <input
                                    type={newType === "date" ? "date" : newType === "number" ? "number" : "text"}
                                    value={newValue}
                                    onChange={(e) => setNewValue(e.target.value)}
                                    placeholder="Value"
                                    className="flex-1 rounded-md border border-input bg-background px-3 py-1.5 text-sm"
                                />
                                <Button size="sm" onClick={handleCreateCustom} disabled={!newKey.trim()}>
                                    Add
                                </Button>
                                <Button size="sm" variant="ghost" onClick={() => setShowAddForm(false)}>
                                    <X className="h-4 w-4" />
                                </Button>
                            </div>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}