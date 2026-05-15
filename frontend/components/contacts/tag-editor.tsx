"use client";

import React, { useState } from "react";
import { X, Plus, Tag as TagIcon, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

interface TagEditorProps {
    tags: string[];
    availableTags?: { id: number; name: string; color: string }[];
    onAddTag?: (tag: string) => void;
    onRemoveTag?: (tag: string) => void;
    onCreateTag?: (tag: string) => void;
    isLoading?: boolean;
    editable?: boolean;
}

export function TagEditor({
    tags = [],
    availableTags = [],
    onAddTag,
    onRemoveTag,
    onCreateTag,
    isLoading = false,
    editable = true,
}: TagEditorProps) {
    const [newTag, setNewTag] = useState("");
    const [showInput, setShowInput] = useState(false);
    const [isCreating, setIsCreating] = useState(false);

    const existingAvailableTags = availableTags.filter(
        (t) => !tags.includes(t.name)
    );

    const handleAddTag = (tagName: string) => {
        if (onAddTag && tagName.trim()) {
            onAddTag(tagName.trim());
        }
    };

    const handleRemoveTag = (tagName: string) => {
        if (onRemoveTag) {
            onRemoveTag(tagName);
        }
    };

    const handleCreateAndAdd = async () => {
        if (!newTag.trim()) return;

        setIsCreating(true);
        try {
            if (onCreateTag) {
                await onCreateTag(newTag.trim());
            }
            if (onAddTag) {
                onAddTag(newTag.trim());
            }
            setNewTag("");
            setShowInput(false);
        } finally {
            setIsCreating(false);
        }
    };

    const handleSelectExisting = (tagName: string) => {
        handleAddTag(tagName);
    };

    if (!editable) {
        return (
            <div className="flex flex-wrap gap-2">
                {tags.length === 0 ? (
                    <span className="text-sm text-muted-foreground">No tags</span>
                ) : (
                    tags.map((tag) => (
                        <Badge key={tag} variant="outline" className="text-xs">
                            {tag}
                        </Badge>
                    ))
                )}
            </div>
        );
    }

    return (
        <div className="space-y-3">
            <div className="flex flex-wrap gap-2">
                {tags.map((tag) => (
                    <Badge
                        key={tag}
                        variant="secondary"
                        className="flex items-center gap-1 pr-1"
                    >
                        <TagIcon className="h-3 w-3" />
                        {tag}
                        {onRemoveTag && (
                            <button
                                onClick={() => handleRemoveTag(tag)}
                                className="ml-1 hover:text-destructive"
                            >
                                <X className="h-3 w-3" />
                            </button>
                        )}
                    </Badge>
                ))}

                {!showInput && onAddTag && (
                    <button
                        onClick={() => setShowInput(true)}
                        className="inline-flex items-center gap-1 px-2 py-1 text-xs text-muted-foreground hover:text-foreground border border-dashed rounded-md transition-colors"
                    >
                        <Plus className="h-3 w-3" />
                        Add tag
                    </button>
                )}
            </div>

            {showInput && (
                <div className="space-y-2">
                    {existingAvailableTags.length > 0 && (
                        <div className="flex flex-wrap gap-1">
                            <span className="text-xs text-muted-foreground mr-1">Existing:</span>
                            {existingAvailableTags.map((tag) => (
                                <button
                                    key={tag.id}
                                    onClick={() => handleSelectExisting(tag.name)}
                                    className="inline-flex items-center px-2 py-1 text-xs bg-muted hover:bg-muted/80 rounded-md transition-colors"
                                >
                                    {tag.name}
                                </button>
                            ))}
                        </div>
                    )}

                    <div className="flex gap-2">
                        <input
                            type="text"
                            value={newTag}
                            onChange={(e) => setNewTag(e.target.value)}
                            placeholder="New tag name"
                            className="flex-1 rounded-md border border-input bg-background px-3 py-1.5 text-sm"
                            onKeyDown={(e) => {
                                if (e.key === "Enter") {
                                    handleCreateAndAdd();
                                } else if (e.key === "Escape") {
                                    setShowInput(false);
                                    setNewTag("");
                                }
                            }}
                            autoFocus
                        />
                        <Button
                            size="sm"
                            onClick={handleCreateAndAdd}
                            disabled={isCreating || !newTag.trim()}
                        >
                            {isCreating ? <Loader2 className="h-4 w-4 animate-spin" /> : "Add"}
                        </Button>
                        <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => {
                                setShowInput(false);
                                setNewTag("");
                            }}
                        >
                            <X className="h-4 w-4" />
                        </Button>
                    </div>
                </div>
            )}
        </div>
    );
}