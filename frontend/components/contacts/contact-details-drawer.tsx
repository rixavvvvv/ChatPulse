"use client";

import React, { useState, useEffect, useCallback } from "react";
import { User, Phone, Mail, Calendar, Clock, MessageSquare, Tag, FileText, Loader2, RefreshCw } from "lucide-react";
import { format, parseISO, isValid } from "date-fns";
import { cn } from "@/lib/utils";
import { Drawer } from "@/components/ui/drawer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ActivityTimeline } from "./activity-timeline";
import { TagEditor } from "./tag-editor";
import { AttributeEditor } from "./attribute-editor";
import { Contact } from "@/lib/types/contact";
import {
    useContact,
    useContactActivities,
    useContactNotes,
    useContactAttributes,
    useUpdateContact,
    useAddContactNote,
    useDeleteContactNote,
    useUpdateContactAttributes,
    useCreateTag,
    useTags,
} from "@/hooks/use-contacts";
import type { ContactActivity, ContactNote, ContactAttribute, AttributeDefinition } from "@/lib/types/contact";

interface ContactDetailsDrawerProps {
    contactId: number | null;
    isOpen: boolean;
    onClose: () => void;
}

function formatDate(dateString: string | undefined): string {
    if (!dateString) return "—";
    try {
        const date = parseISO(dateString);
        if (!isValid(date)) return "—";
        return format(date, "MMM d, yyyy 'at' h:mm a");
    } catch {
        return "—";
    }
}

function ProfileSection({ contact }: { contact: Contact }) {
    return (
        <div className="space-y-4">
            <div className="flex items-center gap-4">
                <div className="h-16 w-16 rounded-full bg-muted flex items-center justify-center">
                    <User className="h-8 w-8 text-muted-foreground" />
                </div>
                <div>
                    <h3 className="text-xl font-semibold">{contact.name || "Unknown"}</h3>
                    <p className="text-sm text-muted-foreground">Created {formatDate(contact.created_at)}</p>
                </div>
            </div>

            <div className="grid gap-3">
                <div className="flex items-center gap-3 text-sm">
                    <Phone className="h-4 w-4 text-muted-foreground" />
                    <span className="font-mono">{contact.phone}</span>
                </div>
                {contact.email && (
                    <div className="flex items-center gap-3 text-sm">
                        <Mail className="h-4 w-4 text-muted-foreground" />
                        <span>{contact.email}</span>
                    </div>
                )}
            </div>

            {contact.tags && contact.tags.length > 0 && (
                <div className="pt-2">
                    <p className="text-xs font-medium text-muted-foreground mb-2">Tags</p>
                    <div className="flex flex-wrap gap-1">
                        {contact.tags.map((tag) => (
                            <Badge key={tag} variant="outline" className="text-xs">
                                {tag}
                            </Badge>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
}

function LoadingSkeleton() {
    return (
        <div className="space-y-6 p-6">
            <div className="flex items-center gap-4">
                <div className="h-16 w-16 rounded-full bg-muted animate-pulse" />
                <div className="space-y-2">
                    <div className="h-6 w-32 bg-muted animate-pulse rounded" />
                    <div className="h-4 w-48 bg-muted animate-pulse rounded" />
                </div>
            </div>
            <div className="space-y-3">
                <div className="h-4 w-full bg-muted animate-pulse rounded" />
                <div className="h-4 w-3/4 bg-muted animate-pulse rounded" />
            </div>
        </div>
    );
}

export function ContactDetailsDrawer({
    contactId,
    isOpen,
    onClose,
}: ContactDetailsDrawerProps) {
    const [activeTab, setActiveTab] = useState("activity");

    const { data: contact, isLoading: isContactLoading, refetch: refetchContact } = useContact(contactId!);
    const { data: activities = [], isLoading: isActivitiesLoading } = useContactActivities(contactId!);
    const { data: notes = [], isLoading: isNotesLoading, refetch: refetchNotes } = useContactNotes(contactId!);
    const { data: attributes = [], isLoading: isAttributesLoading } = useContactAttributes(contactId!);
    const { data: availableTags = [] } = useTags();
    const { mutateAsync: createTag } = useCreateTag();

    const updateContactMutation = useUpdateContact();
    const addNoteMutation = useAddContactNote();
    const deleteNoteMutation = useDeleteContactNote();
    const updateAttributesMutation = useUpdateContactAttributes();

    const handleAddNote = useCallback(async (body: string) => {
        if (!contactId) return;
        await addNoteMutation.mutateAsync({ contactId, body });
        refetchNotes();
    }, [contactId, addNoteMutation, refetchNotes]);

    const handleDeleteNote = useCallback(async (noteId: number) => {
        if (!contactId) return;
        await deleteNoteMutation.mutateAsync({ contactId, noteId });
        refetchNotes();
    }, [contactId, deleteNoteMutation, refetchNotes]);

    const handleCreateTag = useCallback(async (tagName: string) => {
        await createTag({ name: tagName });
    }, [createTag]);

    const handleAddTag = useCallback(async (tag: string) => {
        if (!contact || !contactId) return;
        const newTags = [...(contact.tags || []), tag];
        await updateContactMutation.mutateAsync({
            id: contactId,
            data: { tags: newTags },
        });
        refetchContact();
    }, [contact, contactId, updateContactMutation, refetchContact]);

    const handleRemoveTag = useCallback(async (tag: string) => {
        if (!contact || !contactId) return;
        const newTags = (contact.tags || []).filter((t) => t !== tag);
        await updateContactMutation.mutateAsync({
            id: contactId,
            data: { tags: newTags },
        });
        refetchContact();
    }, [contact, contactId, updateContactMutation, refetchContact]);

    const handleUpdateAttribute = useCallback(async (key: string, value: string | number | boolean | null) => {
        if (!contactId) return;
        await updateAttributesMutation.mutateAsync({
            contactId,
            attributes: { [key]: value },
        });
    }, [contactId, updateAttributesMutation]);

    const handleCreateAttribute = useCallback(async (key: string, value: string | number | boolean | null) => {
        if (!contactId) return;
        await updateAttributesMutation.mutateAsync({
            contactId,
            attributes: { [key]: value },
        });
    }, [contactId, updateAttributesMutation]);

    const activitiesWithNotes: ContactActivity[] = React.useMemo(() => {
        const noteActivities: ContactActivity[] = notes.map((note) => ({
            id: note.id,
            contact_id: note.contact_id,
            type: "note_added",
            payload: { body: note.body },
            created_at: note.created_at,
            actor_user_id: note.author_user_id,
        }));
        return [...activities, ...noteActivities].sort(
            (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
        );
    }, [activities, notes]);

    if (isContactLoading) {
        return (
            <Drawer isOpen={isOpen} onClose={onClose} title="Contact Details" size="lg">
                <LoadingSkeleton />
            </Drawer>
        );
    }

    if (!contact) {
        return (
            <Drawer isOpen={isOpen} onClose={onClose} title="Contact Details" size="lg">
                <div className="p-6 text-center text-muted-foreground">
                    Contact not found
                </div>
            </Drawer>
        );
    }

    return (
        <Drawer isOpen={isOpen} onClose={onClose} title="Contact Details" size="lg">
            <div className="space-y-6">
                <ProfileSection contact={contact} />

                <Tabs value={activeTab} onValueChange={setActiveTab}>
                    <TabsList className="w-full">
                        <TabsTrigger value="activity" className="flex-1">
                            <MessageSquare className="h-4 w-4 mr-2" />
                            Activity
                        </TabsTrigger>
                        <TabsTrigger value="attributes" className="flex-1">
                            <FileText className="h-4 w-4 mr-2" />
                            Attributes
                        </TabsTrigger>
                        <TabsTrigger value="notes" className="flex-1">
                            <Tag className="h-4 w-4 mr-2" />
                            Notes
                        </TabsTrigger>
                    </TabsList>

                    <TabsContent value="activity" className="mt-4">
                        <div className="max-h-96 overflow-y-auto">
                            <ActivityTimeline
                                activities={activitiesWithNotes}
                                isLoading={isActivitiesLoading || isNotesLoading}
                                showNoteInput
                                isAddingNote={addNoteMutation.isPending}
                                onAddNote={handleAddNote}
                            />
                        </div>
                    </TabsContent>

                    <TabsContent value="attributes" className="mt-4">
                        <AttributeEditor
                            attributes={attributes}
                            isLoading={isAttributesLoading}
                            editable
                            onUpdate={handleUpdateAttribute}
                            onCreate={handleCreateAttribute}
                        />
                    </TabsContent>

                    <TabsContent value="notes" className="mt-4">
                        <div className="space-y-4">
                            <div className="flex justify-end">
                                <Button
                                    size="sm"
                                    onClick={() => handleAddNote("")}
                                >
                                    Add Note
                                </Button>
                            </div>
                            <div className="space-y-3 max-h-96 overflow-y-auto">
                                {isNotesLoading ? (
                                    Array.from({ length: 3 }).map((_, i) => (
                                        <div key={i} className="p-3 bg-muted/50 rounded-lg">
                                            <div className="h-4 w-full bg-muted animate-pulse rounded mb-2" />
                                            <div className="h-3 w-1/2 bg-muted animate-pulse rounded" />
                                        </div>
                                    ))
                                ) : notes.length === 0 ? (
                                    <p className="text-sm text-muted-foreground text-center py-4">
                                        No notes yet
                                    </p>
                                ) : (
                                    notes.map((note) => (
                                        <div
                                            key={note.id}
                                            className="p-3 bg-muted/50 rounded-lg group"
                                        >
                                            <p className="text-sm whitespace-pre-wrap">{note.body}</p>
                                            <div className="flex items-center justify-between mt-2">
                                                <span className="text-xs text-muted-foreground">
                                                    {formatDate(note.created_at)}
                                                </span>
                                                {!note.deleted_at && (
                                                    <button
                                                        onClick={() => handleDeleteNote(note.id)}
                                                        className="text-xs text-muted-foreground hover:text-red-600 opacity-0 group-hover:opacity-100 transition-opacity"
                                                    >
                                                        Delete
                                                    </button>
                                                )}
                                            </div>
                                        </div>
                                    ))
                                )}
                            </div>
                        </div>
                    </TabsContent>
                </Tabs>

                <div className="flex justify-between pt-4 border-t">
                    <Button
                        variant="outline"
                        size="sm"
                        onClick={() => refetchContact()}
                        disabled={updateContactMutation.isPending}
                    >
                        <RefreshCw className={cn("h-4 w-4 mr-2", updateContactMutation.isPending && "animate-spin")} />
                        Refresh
                    </Button>
                    <Button size="sm" onClick={onClose}>
                        Close
                    </Button>
                </div>
            </div>
        </Drawer>
    );
}