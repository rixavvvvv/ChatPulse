import { apiRequest } from "@/lib/api";
import { getSession } from "@/lib/session";

const BASE_URL = "/conversations";

async function getAuthHeaders(): Promise<string> {
    const session = getSession();
    if (!session) {
        throw new Error("Authentication required");
    }
    return session.access_token;
}

export interface Conversation {
    id: number;
    workspace_id: number;
    contact_id: number;
    channel: string;
    status: string;
    priority: string;
    subject: string | null;
    last_message_preview: string | null;
    last_message_at: string | null;
    unread_count: number;
    created_at: string;
    updated_at: string;
}

export interface ConversationMessage {
    id: number;
    conversation_id: number;
    direction: "inbound" | "outbound";
    sender_type: "contact" | "agent" | "bot" | "system";
    sender_id: number | null;
    content_type: string;
    content: string;
    created_at: string;
}

export async function listConversations(): Promise<Conversation[]> {
    const token = await getAuthHeaders();
    return apiRequest<Conversation[]>(BASE_URL, {}, token);
}

export async function getConversationMessages(conversationId: number): Promise<ConversationMessage[]> {
    const token = await getAuthHeaders();
    return apiRequest<ConversationMessage[]>(`${BASE_URL}/${conversationId}/messages`, {}, token);
}

export async function sendConversationMessage(conversationId: number, content: string): Promise<ConversationMessage> {
    const token = await getAuthHeaders();
    return apiRequest<ConversationMessage>(
        `${BASE_URL}/${conversationId}/messages`,
        {
            method: "POST",
            body: JSON.stringify({ content, content_type: "text", metadata_json: {} }),
        },
        token
    );
}

export async function markConversationRead(conversationId: number): Promise<void> {
    const token = await getAuthHeaders();
    return apiRequest<void>(
        `${BASE_URL}/${conversationId}/read`,
        { method: "POST" },
        token
    );
}
