import { apiClient } from "@/services/api";
import {
    ConversationAssignment,
    ConversationDetails,
    ConversationInternalNote,
    ConversationLabel,
    ConversationLabelAssignment,
    ConversationListItem,
    ConversationMessage,
    UnreadSummary,
} from "@/types";

export interface ConversationListParams {
    status?: string;
    channel?: string;
    priority?: string;
    assigned_to?: number;
    label_id?: number;
    search?: string;
    limit?: number;
    offset?: number;
}

export interface MessagesParams {
    limit?: number;
    before_id?: number;
    after_id?: number;
}

export const inboxService = {
    listConversations: (params: ConversationListParams) =>
        apiClient.get<ConversationListItem[]>("/conversations", { params }),

    getConversation: (conversationId: number) =>
        apiClient.get<ConversationDetails>(`/conversations/${conversationId}`),

    listMessages: (conversationId: number, params: MessagesParams) =>
        apiClient.get<ConversationMessage[]>(`/conversations/${conversationId}/messages`, {
            params,
        }),

    sendMessage: (conversationId: number, content: string) =>
        apiClient.post<ConversationMessage>(`/conversations/${conversationId}/messages`, {
            content,
        }),

    markRead: (conversationId: number, lastReadMessageId?: number) =>
        apiClient.post(`/conversations/${conversationId}/read`, {
            last_read_message_id: lastReadMessageId ?? null,
        }),

    getUnreadSummary: () =>
        apiClient.get<UnreadSummary>("/conversations/unread"),

    assignConversation: (conversationId: number, agentUserId: number, version: number) =>
        apiClient.post<ConversationAssignment>(`/conversations/${conversationId}/assign`, {
            agent_user_id: agentUserId,
            version,
        }),

    unassignConversation: (conversationId: number, version: number) =>
        apiClient.post(`/conversations/${conversationId}/unassign`, {
            version,
        }),

    listNotes: (conversationId: number) =>
        apiClient.get<ConversationInternalNote[]>(`/conversations/${conversationId}/notes`),

    createNote: (conversationId: number, body: string) =>
        apiClient.post<ConversationInternalNote>(`/conversations/${conversationId}/notes`, {
            body,
        }),

    deleteNote: (conversationId: number, noteId: number) =>
        apiClient.delete(`/conversations/${conversationId}/notes/${noteId}`),

    listConversationLabels: (conversationId: number) =>
        apiClient.get<ConversationLabel[]>(`/conversations/${conversationId}/labels`),

    listWorkspaceLabels: () => apiClient.get<ConversationLabel[]>("/conversation-labels"),

    createLabel: (name: string, color: string, description?: string) =>
        apiClient.post<ConversationLabel>("/conversation-labels", {
            name,
            color,
            description,
        }),

    assignLabel: (conversationId: number, labelId: number) =>
        apiClient.post<ConversationLabelAssignment>(
            `/conversations/${conversationId}/labels`,
            { label_id: labelId }
        ),

    removeLabel: (conversationId: number, labelId: number) =>
        apiClient.delete(`/conversations/${conversationId}/labels/${labelId}`),
};
