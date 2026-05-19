import React from "react";
import { Check, CheckCheck, RotateCcw, TriangleAlert } from "lucide-react";
import { cn } from "@/lib/utils";
import { ConversationMessage } from "@/types";
import { formatTime } from "@/lib/utils";

interface MessageBubbleProps {
    message: ConversationMessage;
    isOwn: boolean;
    onRetry?: (message: ConversationMessage) => void;
}

function resolveStatus(message: ConversationMessage): string | null {
    const raw = message.metadata_json?.status || message.metadata_json?.delivery_status || message.metadata_json?.message_status;
    if (typeof raw === "string") {
        return raw.toLowerCase();
    }
    return null;
}

function StatusIndicator({ status }: { status: string | null }) {
    if (!status) return null;
    if (status === "sending" || status === "queued") {
        return <span className="text-[11px] text-blue-100">Sending…</span>;
    }
    if (status === "failed") {
        return <TriangleAlert className="h-3.5 w-3.5 text-rose-200" />;
    }
    if (status === "read") {
        return <CheckCheck className="h-3.5 w-3.5 text-emerald-200" />;
    }
    if (status === "delivered") {
        return <CheckCheck className="h-3.5 w-3.5 text-blue-100" />;
    }
    if (status === "sent") {
        return <Check className="h-3.5 w-3.5 text-blue-100" />;
    }
    return null;
}

export function MessageBubble({ message, isOwn, onRetry }: MessageBubbleProps) {
    const status = resolveStatus(message);
    const mediaUrl = typeof message.metadata_json?.media_url === "string" ? message.metadata_json?.media_url : null;
    const fileName = typeof message.metadata_json?.file_name === "string" ? message.metadata_json?.file_name : null;
    const templateName = typeof message.metadata_json?.template_name === "string" ? message.metadata_json?.template_name : null;
    const templateLanguage = typeof message.metadata_json?.language === "string" ? message.metadata_json?.language : null;
    const templateParams = Array.isArray(message.metadata_json?.body_parameters)
        ? (message.metadata_json?.body_parameters as string[])
        : [];

    return (
        <div className={cn("flex", isOwn ? "justify-end" : "justify-start")}>
            <div
                className={cn(
                    "max-w-[75%] rounded-2xl px-4 py-2 text-sm shadow-sm",
                    isOwn
                        ? "bg-emerald-600 text-white"
                        : "bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800"
                )}
            >
                {message.content_type === "template" ? (
                    <div className="space-y-2">
                        <div className={cn("text-[11px] uppercase tracking-wide", isOwn ? "text-emerald-100" : "text-gray-400")}>
                            Template
                        </div>
                        <div className="font-semibold">{templateName || message.content}</div>
                        {templateLanguage ? (
                            <div className={cn("text-xs", isOwn ? "text-emerald-100" : "text-gray-500")}>{templateLanguage}</div>
                        ) : null}
                        {templateParams.length > 0 ? (
                            <div className={cn("text-xs", isOwn ? "text-emerald-100" : "text-gray-500")}>
                                {templateParams.join(", ")}
                            </div>
                        ) : null}
                    </div>
                ) : null}

                {message.content_type === "image" && mediaUrl ? (
                    <img src={mediaUrl} alt={fileName || "image"} className="mt-2 max-h-64 rounded-lg" />
                ) : null}

                {message.content_type === "document" && mediaUrl ? (
                    <a
                        className={cn("mt-2 inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-xs", isOwn ? "border-emerald-400" : "border-gray-200")}
                        href={mediaUrl}
                        target="_blank"
                        rel="noreferrer"
                    >
                        {fileName || "Open document"}
                    </a>
                ) : null}

                {message.content && message.content_type !== "template" ? (
                    <p className="whitespace-pre-wrap break-words">{message.content}</p>
                ) : null}

                <div className={cn("mt-1 flex items-center justify-end gap-2 text-[11px]", isOwn ? "text-emerald-100" : "text-gray-500 dark:text-gray-400")}>
                    <span>{formatTime(message.created_at)}</span>
                    {isOwn ? <StatusIndicator status={status} /> : null}
                    {isOwn && status === "failed" && onRetry ? (
                        <button
                            className="flex items-center gap-1 text-rose-100 hover:text-white"
                            onClick={() => onRetry(message)}
                        >
                            <RotateCcw className="h-3 w-3" />
                            Retry
                        </button>
                    ) : null}
                </div>
            </div>
        </div>
    );
}
