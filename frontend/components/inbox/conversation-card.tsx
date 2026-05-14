import React from "react";
import { cn } from "@/lib/utils";
import { ConversationListItem } from "@/types";
import { formatRelativeTime } from "@/lib/utils";

interface ConversationCardProps {
    conversation: ConversationListItem;
    isActive: boolean;
    unreadCount?: number;
    onSelect: (conversationId: number) => void;
}

export function ConversationCard({
    conversation,
    isActive,
    unreadCount,
    onSelect,
}: ConversationCardProps) {
    const unread = unreadCount ?? conversation.unread_count;

    return (
        <button
            className={cn(
                "w-full text-left rounded-xl border p-4 transition-colors",
                isActive
                    ? "border-blue-600 bg-blue-50 dark:bg-blue-950"
                    : "border-gray-200 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-900"
            )}
            onClick={() => onSelect(conversation.id)}
        >
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                    <div className="h-10 w-10 rounded-full bg-gray-200 dark:bg-gray-800" />
                    <div>
                        <p className="font-semibold text-sm">Contact #{conversation.contact_id}</p>
                        <p className="text-xs text-gray-500 dark:text-gray-400">
                            {conversation.channel.toUpperCase()}
                        </p>
                    </div>
                </div>
                {unread > 0 && (
                    <span className="text-xs px-2 py-1 rounded-full bg-blue-600 text-white">
                        {unread}
                    </span>
                )}
            </div>

            <div className="mt-3">
                <p className="text-sm text-gray-700 dark:text-gray-300 line-clamp-2">
                    {conversation.last_message_preview || "No messages yet"}
                </p>
                <div className="mt-2 flex items-center justify-between text-xs text-gray-500 dark:text-gray-400">
                    <span className="capitalize">{conversation.status}</span>
                    {conversation.last_message_at && (
                        <span>{formatRelativeTime(conversation.last_message_at)}</span>
                    )}
                </div>
            </div>
        </button>
    );
}
