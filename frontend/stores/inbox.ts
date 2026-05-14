import { create } from "zustand";
import { AgentPresenceStatus } from "@/types";

export interface TypingState {
    conversationId: number;
    userId: number;
}

export interface PresenceState {
    userId: number;
    status: AgentPresenceStatus;
    lastSeenAt?: string | null;
}

export interface ConnectionState {
    status: "connected" | "connecting" | "reconnecting" | "disconnected";
    lastConnectedAt?: string | null;
    lastError?: string | null;
}

interface InboxStore {
    selectedConversationId: number | null;
    search: string;
    filters: {
        status?: string;
        channel?: string;
        priority?: string;
        assignedTo?: number;
        labelId?: number;
    };
    typingByConversation: Record<number, TypingState[]>;
    presenceByUser: Record<number, PresenceState>;
    unreadByConversation: Record<number, number>;
    connection: ConnectionState;
    setSelectedConversation: (conversationId: number | null) => void;
    setSearch: (value: string) => void;
    setFilters: (filters: InboxStore["filters"]) => void;
    setTyping: (conversationId: number, typing: TypingState[]) => void;
    addTyping: (conversationId: number, typing: TypingState) => void;
    removeTyping: (conversationId: number, userId: number) => void;
    setPresence: (userId: number, presence: PresenceState) => void;
    setUnread: (conversationId: number, count: number) => void;
    setConnection: (connection: Partial<ConnectionState>) => void;
}

export const useInboxStore = create<InboxStore>((set) => ({
    selectedConversationId: null,
    search: "",
    filters: {},
    typingByConversation: {},
    presenceByUser: {},
    unreadByConversation: {},
    connection: {
        status: "disconnected",
        lastConnectedAt: null,
        lastError: null,
    },
    setSelectedConversation: (conversationId) => set({ selectedConversationId: conversationId }),
    setSearch: (value) => set({ search: value }),
    setFilters: (filters) => set({ filters }),
    setTyping: (conversationId, typing) =>
        set((state) => ({
            typingByConversation: {
                ...state.typingByConversation,
                [conversationId]: typing,
            },
        })),
    addTyping: (conversationId, typing) =>
        set((state) => {
            const current = state.typingByConversation[conversationId] || [];
            const exists = current.some((item) => item.userId === typing.userId);
            return {
                typingByConversation: {
                    ...state.typingByConversation,
                    [conversationId]: exists ? current : [...current, typing],
                },
            };
        }),
    removeTyping: (conversationId, userId) =>
        set((state) => ({
            typingByConversation: {
                ...state.typingByConversation,
                [conversationId]: (state.typingByConversation[conversationId] || []).filter(
                    (item) => item.userId !== userId
                ),
            },
        })),
    setPresence: (userId, presence) =>
        set((state) => ({
            presenceByUser: {
                ...state.presenceByUser,
                [userId]: presence,
            },
        })),
    setUnread: (conversationId, count) =>
        set((state) => ({
            unreadByConversation: {
                ...state.unreadByConversation,
                [conversationId]: count,
            },
        })),
    setConnection: (connection) =>
        set((state) => ({
            connection: {
                ...state.connection,
                ...connection,
            },
        })),
}));
