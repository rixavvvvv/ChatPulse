import React from "react";
import { Pin, PinOff } from "lucide-react";
import { cn } from "@/lib/utils";
import { ConversationListItem } from "@/types";
import { formatRelativeTime } from "@/lib/utils";

interface ConversationCardProps {
    conversation: ConversationListItem;
    isActive: boolean;
    unreadCount?: number;
    onSelect: (conversationId: number) => void;
    onTogglePin?: (conversationId: number) => void;
    isPinned?: boolean;
}

export function ConversationCard({
    conversation,
    isActive,
    unreadCount,
    onSelect,
    onTogglePin,
    isPinned,
}: ConversationCardProps) {
    const unread = unreadCount ?? conversation.unread_count;

    return (
        <div
            role="button"
            tabIndex={0}
            className={cn(
                "w-full text-left rounded-xl border p-3 transition-colors",
                isActive
                    ? "border-emerald-600 bg-emerald-50 dark:bg-emerald-950"
                    : "border-gray-200 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-900"
            )}
            onClick={() => onSelect(conversation.id)}
            onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    onSelect(conversation.id);
                }
            }}
        >
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                    <div className="h-10 w-10 rounded-full bg-gray-200 dark:bg-gray-800" />
                    <div>
                        <p className="font-semibold text-sm">Contact #{conversation.contact_id}</p>
                        <p className="text-xs text-gray-500 dark:text-gray-400">
                            {conversation.channel.toUpperCase()} · {conversation.status}
                        </p>
                    </div>
                </div>
                <div className="flex items-center gap-2">
                    {typeof onTogglePin === "function" ? (
                        <button
                            type="button"
                            className="rounded-md border px-2 py-1 text-xs text-gray-500 hover:text-gray-900"
                            onClick={(event) => {
                                event.stopPropagation();
                                onTogglePin(conversation.id);
                            }}
                        >
                            {isPinned ? <PinOff className="h-3 w-3" /> : <Pin className="h-3 w-3" />}
                        </button>
                    ) : null}
                    {unread > 0 && (
                        <span className="text-xs px-2 py-1 rounded-full bg-emerald-600 text-white">
                            {unread}
                        </span>
                    )}
                </div>
            </div>

            <div className="mt-3">
                <p className="text-sm text-gray-700 dark:text-gray-300 line-clamp-2">
                    {conversation.last_message_preview || "No messages yet"}
                </p>
                <div className="mt-2 flex items-center justify-between text-xs text-gray-500 dark:text-gray-400">
                    <span className="capitalize">{conversation.priority}</span>
                    {conversation.last_message_at && (
                        <span>{formatRelativeTime(conversation.last_message_at)}</span>
                    )}
                </div>
            </div>
        </div>
    );
}
