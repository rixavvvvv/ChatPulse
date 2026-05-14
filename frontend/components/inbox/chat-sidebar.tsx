import React, { useRef, useEffect } from "react";
import { Search } from "lucide-react";
import { Input } from "@/components/ui/input";
import { ConversationCard } from "@/components/inbox/conversation-card";
import { ConversationListItem } from "@/types";
import { cn } from "@/lib/utils";

interface ChatSidebarProps {
    conversations: ConversationListItem[];
    selectedId: number | null;
    unreadByConversation: Record<number, number>;
    onSelect: (conversationId: number) => void;
    search: string;
    onSearchChange: (value: string) => void;
    filters: {
        status?: string;
        channel?: string;
    };
    onFilterChange: (filters: { status?: string; channel?: string }) => void;
    isLoading?: boolean;
    hasNextPage?: boolean;
    onLoadMore?: () => void;
}

export function ChatSidebar({
    conversations,
    selectedId,
    unreadByConversation,
    onSelect,
    search,
    onSearchChange,
    filters,
    onFilterChange,
    isLoading,
    hasNextPage,
    onLoadMore,
}: ChatSidebarProps) {
    const containerRef = useRef<HTMLDivElement | null>(null);

    useEffect(() => {
        const container = containerRef.current;
        if (!container || !onLoadMore) return;

        const handleScroll = () => {
            if (!hasNextPage || isLoading) return;
            const { scrollTop, scrollHeight, clientHeight } = container;
            if (scrollTop + clientHeight >= scrollHeight - 120) {
                onLoadMore();
            }
        };

        container.addEventListener("scroll", handleScroll);
        return () => container.removeEventListener("scroll", handleScroll);
    }, [hasNextPage, isLoading, onLoadMore]);

    return (
        <aside className="w-full md:w-[360px] border-r border-gray-200 dark:border-gray-800 flex flex-col">
            <div className="p-4 border-b border-gray-200 dark:border-gray-800">
                <div className="relative">
                    <Search className="absolute left-3 top-3 text-gray-400" size={18} />
                    <Input
                        placeholder="Search conversations..."
                        value={search}
                        onChange={(e) => onSearchChange(e.target.value)}
                        className="pl-9"
                    />
                </div>
                <div className="mt-3 grid grid-cols-2 gap-2">
                    <select
                        className="w-full rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 px-2 py-2 text-xs"
                        value={filters.status || ""}
                        onChange={(e) =>
                            onFilterChange({
                                ...filters,
                                status: e.target.value || undefined,
                            })
                        }
                    >
                        <option value="">All Status</option>
                        <option value="open">Open</option>
                        <option value="assigned">Assigned</option>
                        <option value="resolved">Resolved</option>
                        <option value="closed">Closed</option>
                    </select>
                    <select
                        className="w-full rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 px-2 py-2 text-xs"
                        value={filters.channel || ""}
                        onChange={(e) =>
                            onFilterChange({
                                ...filters,
                                channel: e.target.value || undefined,
                            })
                        }
                    >
                        <option value="">All Channels</option>
                        <option value="whatsapp">WhatsApp</option>
                        <option value="sms">SMS</option>
                        <option value="email">Email</option>
                        <option value="web">Web</option>
                    </select>
                </div>
            </div>

            <div
                ref={containerRef}
                className={cn(
                    "flex-1 overflow-y-auto p-3 space-y-3",
                    isLoading && "opacity-70"
                )}
            >
                {conversations.map((conversation) => (
                    <ConversationCard
                        key={conversation.id}
                        conversation={conversation}
                        isActive={selectedId === conversation.id}
                        unreadCount={unreadByConversation[conversation.id]}
                        onSelect={onSelect}
                    />
                ))}
                {isLoading && (
                    <p className="text-center text-sm text-gray-500">Loading conversations...</p>
                )}
                {!isLoading && conversations.length === 0 && (
                    <p className="text-center text-sm text-gray-500">No conversations found</p>
                )}
                {hasNextPage && !isLoading && (
                    <div className="text-center text-xs text-gray-400 py-2">Scroll to load more</div>
                )}
            </div>
        </aside>
    );
}
