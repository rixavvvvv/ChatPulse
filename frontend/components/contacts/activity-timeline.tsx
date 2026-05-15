"use client";

import React from "react";
import { format, parseISO, isValid, isToday, isYesterday, isThisWeek, isThisMonth } from "date-fns";
import { Mail, MessageSquare, Tag, FileText, Phone, Plus, Trash2, Edit, Send, CheckCircle, XCircle, AlertCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ContactActivity } from "@/lib/types/contact";

interface ActivityTimelineProps {
    activities: ContactActivity[];
    isLoading?: boolean;
    onAddNote?: (body: string) => void;
    onDeleteNote?: (noteId: number) => void;
    showNoteInput?: boolean;
    isAddingNote?: boolean;
}

const activityIcons: Record<string, React.ComponentType<{ className?: string }>> = {
    message_sent: MessageSquare,
    message_delivered: CheckCircle,
    message_read: Mail,
    message_failed: XCircle,
    contact_created: Plus,
    contact_updated: Edit,
    tag_added: Tag,
    tag_removed: Tag,
    note_added: FileText,
    note_deleted: Trash2,
    campaign_started: Send,
    campaign_completed: CheckCircle,
};

const activityLabels: Record<string, string> = {
    message_sent: "Message sent",
    message_delivered: "Message delivered",
    message_read: "Message read",
    message_failed: "Message failed",
    contact_created: "Contact created",
    contact_updated: "Contact updated",
    tag_added: "Tag added",
    tag_removed: "Tag removed",
    note_added: "Note added",
    note_deleted: "Note deleted",
    campaign_started: "Campaign started",
    campaign_completed: "Campaign completed",
};

function formatActivityDate(dateString: string): string {
    try {
        const date = parseISO(dateString);
        if (!isValid(date)) return "Unknown date";

        if (isToday(date)) return "Today";
        if (isYesterday(date)) return "Yesterday";
        if (isThisWeek(date)) return format(date, "EEEE");
        if (isThisMonth(date)) return format(date, "MMM d");
        return format(date, "MMM d, yyyy");
    } catch {
        return "Unknown date";
    }
}

function formatActivityTime(dateString: string): string {
    try {
        const date = parseISO(dateString);
        if (!isValid(date)) return "";
        return format(date, "h:mm a");
    } catch {
        return "";
    }
}

function ActivityIcon({ type }: { type: string }) {
    const Icon = activityIcons[type] || AlertCircle;
    return <Icon className="h-4 w-4" />;
}

function ActivityContent({ activity }: { activity: ContactActivity }) {
    const payload = activity.payload as Record<string, unknown>;

    switch (activity.type) {
        case "tag_added":
            return (
                <span>
                    Added tag <strong>{payload.tag_name as string}</strong>
                </span>
            );
        case "tag_removed":
            return (
                <span>
                    Removed tag <strong>{payload.tag_name as string}</strong>
                </span>
            );
        case "note_added":
            return (
                <span>
                    Added note: <em>{(payload.body as string || "").slice(0, 50)}...</em>
                </span>
            );
        case "message_sent":
            return (
                <span>
                    Sent message to <strong>{payload.recipient_phone as string}</strong>
                </span>
            );
        case "message_delivered":
            return (
                <span>
                    Message delivered to <strong>{payload.recipient_phone as string}</strong>
                </span>
            );
        case "message_failed":
            return (
                <span>
                    Message failed: <strong className="text-red-600">{payload.error as string}</strong>
                </span>
            );
        default:
            return <span>{activityLabels[activity.type] || activity.type}</span>;
    }
}

function groupActivitiesByDate(activities: ContactActivity[]): Map<string, ContactActivity[]> {
    const groups = new Map<string, ContactActivity[]>();

    for (const activity of activities) {
        const dateKey = formatActivityDate(activity.created_at);
        const existing = groups.get(dateKey) || [];
        groups.set(dateKey, [...existing, activity]);
    }

    return groups;
}

export function ActivityTimeline({
    activities,
    isLoading,
    onAddNote,
    onDeleteNote,
    showNoteInput = false,
    isAddingNote = false,
}: ActivityTimelineProps) {
    const [noteText, setNoteText] = React.useState("");
    const [showInput, setShowInput] = React.useState(showNoteInput);

    const groupedActivities = groupActivitiesByDate(activities);

    const handleAddNote = () => {
        if (noteText.trim() && onAddNote) {
            onAddNote(noteText.trim());
            setNoteText("");
            setShowInput(false);
        }
    };

    if (isLoading) {
        return (
            <div className="space-y-3">
                {Array.from({ length: 5 }).map((_, i) => (
                    <div key={i} className="flex gap-3">
                        <div className="h-8 w-8 rounded-full bg-muted animate-pulse" />
                        <div className="flex-1 space-y-2">
                            <div className="h-4 w-32 bg-muted animate-pulse rounded" />
                            <div className="h-3 w-48 bg-muted animate-pulse rounded" />
                        </div>
                    </div>
                ))}
            </div>
        );
    }

    if (activities.length === 0) {
        return (
            <div className="text-center py-8 text-muted-foreground">
                <MessageSquare className="mx-auto h-8 w-8 mb-2 opacity-50" />
                <p className="text-sm">No activity yet</p>
            </div>
        );
    }

    return (
        <div className="space-y-6">
            {Array.from(groupedActivities.entries()).map(([date, dateActivities]) => (
                <div key={date}>
                    <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3">
                        {date}
                    </h4>
                    <div className="space-y-4">
                        {dateActivities.map((activity) => (
                            <div key={activity.id} className="flex gap-3">
                                <div className="flex-shrink-0">
                                    <div className="h-8 w-8 rounded-full bg-muted flex items-center justify-center">
                                        <ActivityIcon type={activity.type} />
                                    </div>
                                </div>
                                <div className="flex-1 min-w-0">
                                    <div className="flex items-center gap-2">
                                        <span className="text-sm font-medium">
                                            {activityLabels[activity.type] || activity.type}
                                        </span>
                                        <span className="text-xs text-muted-foreground">
                                            {formatActivityTime(activity.created_at)}
                                        </span>
                                    </div>
                                    <p className="text-sm text-muted-foreground mt-1">
                                        <ActivityContent activity={activity} />
                                    </p>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            ))}

            {showInput && (
                <div className="flex gap-2">
                    <input
                        type="text"
                        value={noteText}
                        onChange={(e) => setNoteText(e.target.value)}
                        placeholder="Add a note..."
                        className="flex-1 rounded-md border border-input bg-background px-3 py-2 text-sm"
                        onKeyDown={(e) => e.key === "Enter" && handleAddNote()}
                    />
                    <button
                        onClick={handleAddNote}
                        disabled={isAddingNote || !noteText.trim()}
                        className="px-3 py-2 bg-primary text-primary-foreground rounded-md text-sm disabled:opacity-50"
                    >
                        {isAddingNote ? "..." : "Add"}
                    </button>
                </div>
            )}
        </div>
    );
}