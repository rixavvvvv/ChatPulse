import { useMemo } from "react";
import { ConversationMessage } from "@/types";

export interface MessageGroup {
    date: string;
    messages: ConversationMessage[];
}

export function useMessageGroups(messages: ConversationMessage[]) {
    return useMemo(() => {
        const groups: MessageGroup[] = [];
        const byDate = new Map<string, ConversationMessage[]>();

        messages.forEach((message) => {
            const day = new Date(message.created_at).toDateString();
            const existing = byDate.get(day) || [];
            existing.push(message);
            byDate.set(day, existing);
        });

        byDate.forEach((value, key) => {
            groups.push({ date: key, messages: value });
        });

        groups.sort(
            (a, b) =>
                new Date(a.messages[0].created_at).getTime() -
                new Date(b.messages[0].created_at).getTime()
        );

        return groups;
    }, [messages]);
}
