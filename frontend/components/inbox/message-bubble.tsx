import React from "react";
import { cn } from "@/lib/utils";
import { ConversationMessage } from "@/types";
import { formatTime } from "@/lib/utils";

interface MessageBubbleProps {
    message: ConversationMessage;
    isOwn: boolean;
}

export function MessageBubble({ message, isOwn }: MessageBubbleProps) {
    return (
        <div className={cn("flex", isOwn ? "justify-end" : "justify-start")}>
            <div
                className={cn(
                    "max-w-[70%] rounded-2xl px-4 py-2 text-sm shadow-sm",
                    isOwn
                        ? "bg-blue-600 text-white"
                        : "bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800"
                )}
            >
                <p className="whitespace-pre-wrap break-words">{message.content}</p>
                <div
                    className={cn(
                        "mt-1 text-[11px] flex justify-end",
                        isOwn ? "text-blue-100" : "text-gray-500 dark:text-gray-400"
                    )}
                >
                    {formatTime(message.created_at)}
                </div>
            </div>
        </div>
    );
}
