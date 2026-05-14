"use client";

import React, { useMemo, useEffect } from "react";
import { PageLayout } from "@/components/layout/page-layout";
import { ChatSidebar } from "@/components/inbox/chat-sidebar";
import { ChatWindow } from "@/components/inbox/chat-window";
import { MessageComposer } from "@/components/inbox/message-composer";
import { AssignmentPanel } from "@/components/inbox/assignment-panel";
import { InternalNotes } from "@/components/inbox/internal-notes";
import { LabelsPanel } from "@/components/inbox/labels-panel";
import { ConnectionStatus } from "@/components/inbox/connection-status";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useInboxStore } from "@/stores/inbox";
import {
    useConversationDetails,
    useConversationLabels,
    useConversationLabelAssignments,
    useConversationList,
    useConversationMessages,
    useConversationNotes,
    useSendMessageMutation,
    useUnreadSummary,
    useCreateNoteMutation,
    useAssignConversation,
    useUnassignConversation,
} from "@/hooks/inbox/useInboxQueries";
import { useInboxSocket } from "@/hooks/inbox/useInboxSocket";
import { inboxService } from "@/services/inbox/inbox-service";
import { useAuthStore } from "@/stores/auth";
import { useWebSocket } from "@/websocket/provider";

export default function InboxPage() {
    const {
        selectedConversationId,
        setSelectedConversation,
        search,
        setSearch,
        filters,
        unreadByConversation,
        setUnread,
        connection,
        setFilters,
    } = useInboxStore();

    const { user } = useAuthStore();
    const { socket } = useWebSocket();

    useInboxSocket();

    const { data: unreadSummary } = useUnreadSummary();

    useEffect(() => {
        if (!unreadSummary?.data) return;
        unreadSummary.data.conversations.forEach((item) => {
            setUnread(item.conversation_id, item.unread_count);
        });
    }, [unreadSummary, setUnread]);

    const conversationListQuery = useConversationList({
        search: search || undefined,
        status: filters.status,
        channel: filters.channel,
        priority: filters.priority,
        assigned_to: filters.assignedTo,
        label_id: filters.labelId,
    });

    const conversations = useMemo(() => {
        if (!conversationListQuery.data?.pages) return [];
        return conversationListQuery.data.pages.flatMap((page) => page.data);
    }, [conversationListQuery.data]);

    const conversation = useConversationDetails(selectedConversationId ?? undefined);
    const messagesQuery = useConversationMessages(selectedConversationId ?? undefined);

    const messages = useMemo(() => {
        if (!messagesQuery.data?.pages) return [];
        return messagesQuery.data.pages.flatMap((page) => page.data);
    }, [messagesQuery.data]);

    const sendMessageMutation = useSendMessageMutation(selectedConversationId ?? undefined);
    const notesQuery = useConversationNotes(selectedConversationId ?? undefined);
    const createNoteMutation = useCreateNoteMutation(selectedConversationId ?? undefined);
    const labelsQuery = useConversationLabels();
    const assignedLabelsQuery = useConversationLabelAssignments(selectedConversationId ?? undefined);
    const assignMutation = useAssignConversation();
    const unassignMutation = useUnassignConversation();

    const typing = useInboxStore((state) =>
        selectedConversationId
            ? state.typingByConversation[selectedConversationId] || []
            : []
    );

    const agents = [
        { id: user?.id || 0, name: user ? `${user.first_name} ${user.last_name}` : "Me" },
    ];

    const handleSelectConversation = async (conversationId: number) => {
        setSelectedConversation(conversationId);
        await inboxService.markRead(conversationId);
        setUnread(conversationId, 0);
    };

    return (
        <PageLayout
            title="Shared Inbox"
            description="Manage conversations, assign agents, and respond in real-time."
            actions={<ConnectionStatus status={connection.status} />}
        >
            <div className="flex flex-col lg:flex-row rounded-xl border border-gray-200 dark:border-gray-800 overflow-hidden bg-white dark:bg-gray-950">
                <ChatSidebar
                    conversations={conversations}
                    selectedId={selectedConversationId}
                    unreadByConversation={unreadByConversation}
                    onSelect={handleSelectConversation}
                    search={search}
                    onSearchChange={setSearch}
                    filters={{ status: filters.status, channel: filters.channel }}
                    onFilterChange={(next) =>
                        setFilters({
                            ...filters,
                            status: next.status,
                            channel: next.channel,
                        })
                    }
                    isLoading={conversationListQuery.isFetching}
                    hasNextPage={conversationListQuery.hasNextPage}
                    onLoadMore={() => conversationListQuery.fetchNextPage()}
                />

                <div className="flex-1 flex flex-col">
                    <ChatWindow
                        conversation={conversation.data?.data}
                        messages={messages}
                        isLoading={messagesQuery.isFetching}
                        isTyping={typing.length > 0}
                        onLoadMore={() => messagesQuery.fetchNextPage()}
                        hasMore={messagesQuery.hasNextPage}
                    />
                    <MessageComposer
                        onSend={(text) => sendMessageMutation.mutate(text)}
                        disabled={!selectedConversationId || sendMessageMutation.isPending}
                        onTypingStart={() => {
                            if (!selectedConversationId) return;
                            socket?.emit("typing.start", {
                                conversation_id: selectedConversationId,
                            });
                        }}
                        onTypingStop={() => {
                            if (!selectedConversationId) return;
                            socket?.emit("typing.stop", {
                                conversation_id: selectedConversationId,
                            });
                        }}
                    />
                </div>

                <div className="w-full lg:w-[320px] border-l border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-gray-900 p-4 space-y-6">
                    <Card>
                        <CardHeader>
                            <CardTitle>Assignment</CardTitle>
                        </CardHeader>
                        <CardContent>
                            <AssignmentPanel
                                assignedAgentId={undefined}
                                agents={agents}
                                onAssign={(agentId) => {
                                    if (!conversation.data?.data) return;
                                    assignMutation.mutate({
                                        conversationId: conversation.data.data.id,
                                        agentUserId: agentId,
                                        version: conversation.data.data.version,
                                    });
                                }}
                                onUnassign={() => {
                                    if (!conversation.data?.data) return;
                                    unassignMutation.mutate({
                                        conversationId: conversation.data.data.id,
                                        version: conversation.data.data.version,
                                    });
                                }}
                            />
                        </CardContent>
                    </Card>

                    <Card>
                        <CardHeader>
                            <CardTitle>Labels</CardTitle>
                        </CardHeader>
                        <CardContent>
                            <LabelsPanel
                                labels={labelsQuery.data?.data || []}
                                assigned={assignedLabelsQuery.data?.data || []}
                                onAssign={(labelId) => {
                                    if (!selectedConversationId) return;
                                    inboxService.assignLabel(selectedConversationId, labelId);
                                }}
                                onRemove={(labelId) => {
                                    if (!selectedConversationId) return;
                                    inboxService.removeLabel(selectedConversationId, labelId);
                                }}
                            />
                        </CardContent>
                    </Card>

                    <Card>
                        <CardHeader>
                            <CardTitle>Internal Notes</CardTitle>
                        </CardHeader>
                        <CardContent>
                            <InternalNotes
                                notes={notesQuery.data?.data || []}
                                onAddNote={(body) => createNoteMutation.mutate(body)}
                                isLoading={createNoteMutation.isPending}
                            />
                        </CardContent>
                    </Card>
                </div>
            </div>
        </PageLayout>
    );
}
