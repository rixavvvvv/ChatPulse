import React, { useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ConversationInternalNote } from "@/types";
import { formatDateTime } from "@/lib/utils";

interface InternalNotesProps {
    notes: ConversationInternalNote[];
    onAddNote: (body: string) => void;
    isLoading?: boolean;
}

export function InternalNotes({ notes, onAddNote, isLoading }: InternalNotesProps) {
    const [body, setBody] = useState("");

    const handleAdd = () => {
        if (!body.trim()) return;
        onAddNote(body.trim());
        setBody("");
    };

    return (
        <div className="space-y-4">
            <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold">Internal Notes</h3>
            </div>

            <div className="space-y-3">
                {notes.map((note) => (
                    <div key={note.id} className="rounded-lg border border-gray-200 dark:border-gray-800 p-3">
                        <p className="text-sm text-gray-700 dark:text-gray-200">{note.body}</p>
                        <p className="text-xs text-gray-500 mt-2">{formatDateTime(note.created_at)}</p>
                    </div>
                ))}
                {notes.length === 0 && (
                    <p className="text-sm text-gray-500">No notes yet</p>
                )}
            </div>

            <div className="space-y-2">
                <Textarea
                    value={body}
                    onChange={(e) => setBody(e.target.value)}
                    placeholder="Add internal note..."
                    rows={3}
                />
                <Button onClick={handleAdd} disabled={isLoading} className="w-full">
                    Add Note
                </Button>
            </div>
        </div>
    );
}
