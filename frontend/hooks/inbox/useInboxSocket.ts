import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useWebSocket } from "@/websocket/provider";
import { useInboxStore } from "@/stores/inbox";

interface TypingPayload {
    conversation_id: number;
    user_id: number;
}

interface PresencePayload {
    user_id: number;
    status: "online" | "away" | "busy" | "offline";
    last_seen_at?: string | null;
}

interface UnreadPayload {
    conversation_id: number;
    unread_count: number;
}

interface MessagePayload {
    conversation_id: number;
}

export function useInboxSocket() {
    const { socket, isConnected } = useWebSocket();
    const queryClient = useQueryClient();
    const { addTyping, removeTyping, setPresence, setUnread, setConnection } = useInboxStore();

    useEffect(() => {
        setConnection({
            status: isConnected ? "connected" : "disconnected",
            lastConnectedAt: isConnected ? new Date().toISOString() : undefined,
        });
    }, [isConnected, setConnection]);

    useEffect(() => {
        if (!socket) return;

        const onReconnectAttempt = () => {
            setConnection({ status: "reconnecting" });
        };

        const onConnect = () => {
            setConnection({ status: "connected", lastConnectedAt: new Date().toISOString() });
        };

        const onDisconnect = () => {
            setConnection({ status: "disconnected" });
        };

        const onTypingStart = (payload: TypingPayload) => {
            addTyping(payload.conversation_id, {
                conversationId: payload.conversation_id,
                userId: payload.user_id,
            });
        };

        const onTypingStop = (payload: TypingPayload) => {
            removeTyping(payload.conversation_id, payload.user_id);
        };

        const onPresenceUpdate = (payload: PresencePayload) => {
            setPresence(payload.user_id, {
                userId: payload.user_id,
                status: payload.status,
                lastSeenAt: payload.last_seen_at ?? null,
            });
        };

        const onUnreadUpdate = (payload: UnreadPayload) => {
            setUnread(payload.conversation_id, payload.unread_count);
        };

        const onConversationUpdated = () => {
            queryClient.invalidateQueries({ queryKey: ["inbox", "conversations"] });
        };

        const onMessageEvent = (payload: MessagePayload) => {
            queryClient.invalidateQueries({
                queryKey: ["inbox", "messages", payload.conversation_id],
            });
            queryClient.invalidateQueries({ queryKey: ["inbox", "conversations"] });
        };

        socket.on("reconnect_attempt", onReconnectAttempt);
        socket.on("connect", onConnect);
        socket.on("disconnect", onDisconnect);

        socket.on("typing.start", onTypingStart);
        socket.on("typing.stop", onTypingStop);
        socket.on("typing_start", onTypingStart);
        socket.on("typing_stop", onTypingStop);
        socket.on("presence.update", onPresenceUpdate);
        socket.on("presence_update", onPresenceUpdate);
        socket.on("unread.updated", onUnreadUpdate);
        socket.on("unread_updated", onUnreadUpdate);

        socket.on("conversation.updated", onConversationUpdated);
        socket.on("conversation.assigned", onConversationUpdated);
        socket.on("conversation_updated", onConversationUpdated);
        socket.on("conversation_assigned", onConversationUpdated);
        socket.on("message.received", onMessageEvent);
        socket.on("message.sent", onMessageEvent);
        socket.on("message_received", onMessageEvent);
        socket.on("message_sent", onMessageEvent);

        return () => {
            socket.off("reconnect_attempt", onReconnectAttempt);
            socket.off("connect", onConnect);
            socket.off("disconnect", onDisconnect);
            socket.off("typing.start", onTypingStart);
            socket.off("typing.stop", onTypingStop);
            socket.off("typing_start", onTypingStart);
            socket.off("typing_stop", onTypingStop);
            socket.off("presence.update", onPresenceUpdate);
            socket.off("presence_update", onPresenceUpdate);
            socket.off("unread.updated", onUnreadUpdate);
            socket.off("unread_updated", onUnreadUpdate);
            socket.off("conversation.updated", onConversationUpdated);
            socket.off("conversation.assigned", onConversationUpdated);
            socket.off("conversation_updated", onConversationUpdated);
            socket.off("conversation_assigned", onConversationUpdated);
            socket.off("message.received", onMessageEvent);
            socket.off("message.sent", onMessageEvent);
            socket.off("message_received", onMessageEvent);
            socket.off("message_sent", onMessageEvent);
        };
    }, [socket, queryClient, addTyping, removeTyping, setPresence, setUnread, setConnection]);
}
