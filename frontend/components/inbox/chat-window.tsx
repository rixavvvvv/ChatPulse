import React, { useEffect, useRef } from "react";
import { ConversationDetails, ConversationMessage } from "@/types";
import { MessageBubble } from "@/components/inbox/message-bubble";
import { TypingIndicator } from "@/components/inbox/typing-indicator";
import { useMessageGroups } from "@/hooks/inbox/useMessageGroups";
import { cn } from "@/lib/utils";

interface ChatWindowProps {
    conversation?: ConversationDetails | null;
    messages: ConversationMessage[];
    isLoading?: boolean;
    isTyping?: boolean;
    onLoadMore?: () => void;
    hasMore?: boolean;
    onRetryMessage?: (message: ConversationMessage) => void;
}

export function ChatWindow({
    conversation,
    messages,
    isLoading,
    isTyping,
    onLoadMore,
    hasMore,
    onRetryMessage,
}: ChatWindowProps) {
    const containerRef = useRef<HTMLDivElement | null>(null);
    const groups = useMessageGroups(messages);

    useEffect(() => {
        const container = containerRef.current;
        if (container) {
            container.scrollTop = container.scrollHeight;
        }
    }, [conversation?.id]);

    const handleScroll = () => {
        const container = containerRef.current;
        if (!container || !onLoadMore || !hasMore || isLoading) return;
        if (container.scrollTop <= 100) {
            onLoadMore();
        }
    };

    return (
        <div className="flex-1 flex flex-col border-r border-gray-200 dark:border-gray-800">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-gray-200 dark:border-gray-800 px-4 py-3">
                <div>
                    <h2 className="text-lg font-semibold">
                        {conversation ? `Conversation #${conversation.id}` : "Select a conversation"}
                    </h2>
                    <div className="flex flex-wrap items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
                        {conversation?.channel ? (
                            <span className="rounded-full border px-2 py-0.5">{conversation.channel}</span>
                        ) : null}
                        {conversation?.status ? (
                            <span className="rounded-full border px-2 py-0.5">{conversation.status}</span>
                        ) : null}
                        {conversation?.priority ? (
                            <span className="rounded-full border px-2 py-0.5">{conversation.priority}</span>
                        ) : null}
                    </div>
                </div>
                {conversation?.subject ? (
                    <div className="text-xs text-gray-500">{conversation.subject}</div>
                ) : null}
            </div>

            <div
                ref={containerRef}
                onScroll={handleScroll}
                className={cn(
                    "flex-1 overflow-y-auto p-4 space-y-6 bg-slate-50 dark:bg-gray-900",
                    isLoading && "opacity-70"
                )}
            >
                {hasMore && (
                    <div className="text-center text-xs text-gray-400">Scroll up to load more</div>
                )}
                {groups.map((group) => (
                    <div key={group.date} className="space-y-4">
                        <div className="text-center text-xs text-gray-400">{group.date}</div>
                        <div className="space-y-3">
                            {group.messages.map((message) => (
                                <MessageBubble
                                    key={message.id}
                                    message={message}
                                    isOwn={message.direction === "outbound"}
                                    onRetry={onRetryMessage}
                                />
                            ))}
                        </div>
                    </div>
                ))}
                {messages.length === 0 && !isLoading && (
                    <div className="text-center text-gray-500 text-sm">No messages yet</div>
                )}
            </div>

            <div className="px-4 py-2 border-t border-gray-200 dark:border-gray-800">
                <TypingIndicator isActive={!!isTyping} />
            </div>
        </div>
    );
}
