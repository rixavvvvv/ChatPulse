import React, { useMemo, useState } from "react";
import { Image, Paperclip, Send, Smile, Zap } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";

type ComposerPayload = {
    content: string;
    content_type: string;
    metadata_json?: Record<string, unknown>;
};

interface MessageComposerProps {
    onSend: (payload: ComposerPayload) => void;
    disabled?: boolean;
    onTypingStart?: () => void;
    onTypingStop?: () => void;
}

export function MessageComposer({ onSend, disabled, onTypingStart, onTypingStop }: MessageComposerProps) {
    const [message, setMessage] = useState("");
    const [mode, setMode] = useState<"text" | "template">("text");
    const [emojiOpen, setEmojiOpen] = useState(false);
    const [attachmentUrl, setAttachmentUrl] = useState("");
    const [attachmentName, setAttachmentName] = useState("");
    const [attachmentType, setAttachmentType] = useState<"image" | "document">("image");
    const [templateName, setTemplateName] = useState("");
    const [templateLanguage, setTemplateLanguage] = useState("en_US");
    const [templateParams, setTemplateParams] = useState("");
    const [typingTimeout, setTypingTimeout] = useState<ReturnType<typeof setTimeout> | null>(null);

    const emojiList = useMemo(
        () => ["😀", "😅", "😉", "😍", "👍", "🙏", "🎉", "✅"],
        [],
    );

    const handleSend = () => {
        if (disabled) return;

        if (mode === "template") {
            if (!templateName.trim()) return;
            const params = templateParams
                .split(",")
                .map((value) => value.trim())
                .filter(Boolean);
            onSend({
                content: templateName.trim(),
                content_type: "template",
                metadata_json: {
                    template_name: templateName.trim(),
                    language: templateLanguage.trim() || "en_US",
                    body_parameters: params,
                },
            });
            setTemplateName("");
            setTemplateParams("");
            return;
        }

        if (!message.trim() && !attachmentUrl.trim()) return;

        if (attachmentUrl.trim()) {
            onSend({
                content: message.trim() || attachmentName || attachmentUrl.trim(),
                content_type: attachmentType,
                metadata_json: {
                    media_url: attachmentUrl.trim(),
                    file_name: attachmentName.trim() || undefined,
                },
            });
            setAttachmentUrl("");
            setAttachmentName("");
            setMessage("");
            return;
        }

        onSend({
            content: message.trim(),
            content_type: "text",
            metadata_json: { status: "sent" },
        });
        setMessage("");
    };

    return (
        <div className="border-t border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-950">
            <div className="flex flex-wrap items-center gap-2 px-4 pt-3">
                <Button
                    variant={mode === "text" ? "default" : "outline"}
                    size="sm"
                    onClick={() => setMode("text")}
                >
                    Chat
                </Button>
                <Button
                    variant={mode === "template" ? "default" : "outline"}
                    size="sm"
                    onClick={() => setMode("template")}
                >
                    <Zap className="mr-2 h-4 w-4" />
                    Template
                </Button>
                <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setEmojiOpen((prev) => !prev)}
                >
                    <Smile className="mr-2 h-4 w-4" />
                    Emoji
                </Button>
            </div>

            {emojiOpen ? (
                <div className="flex flex-wrap gap-2 px-4 pt-3">
                    {emojiList.map((emoji) => (
                        <button
                            key={emoji}
                            className="rounded-md border border-gray-200 px-2 py-1 text-base"
                            onClick={() => setMessage((prev) => `${prev}${emoji}`)}
                        >
                            {emoji}
                        </button>
                    ))}
                </div>
            ) : null}

            {mode === "template" ? (
                <div className="grid gap-3 px-4 py-3 md:grid-cols-2">
                    <div className="space-y-2">
                        <label className="text-xs font-semibold uppercase text-gray-500">Template name</label>
                        <Input
                            value={templateName}
                            onChange={(event) => setTemplateName(event.target.value)}
                            placeholder="order_update"
                            disabled={disabled}
                        />
                    </div>
                    <div className="space-y-2">
                        <label className="text-xs font-semibold uppercase text-gray-500">Language</label>
                        <Input
                            value={templateLanguage}
                            onChange={(event) => setTemplateLanguage(event.target.value)}
                            placeholder="en_US"
                            disabled={disabled}
                        />
                    </div>
                    <div className="space-y-2 md:col-span-2">
                        <label className="text-xs font-semibold uppercase text-gray-500">Body parameters</label>
                        <Input
                            value={templateParams}
                            onChange={(event) => setTemplateParams(event.target.value)}
                            placeholder="Jane, Order #1234"
                            disabled={disabled}
                        />
                    </div>
                </div>
            ) : (
                <div className="space-y-3 px-4 py-3">
                    <div className="grid gap-3 md:grid-cols-[160px_1fr]">
                        <div className="space-y-2">
                            <label className="text-xs font-semibold uppercase text-gray-500">Attachment</label>
                            <div className="flex gap-2">
                                <Button
                                    variant={attachmentType === "image" ? "default" : "outline"}
                                    size="sm"
                                    onClick={() => setAttachmentType("image")}
                                >
                                    <Image className="mr-2 h-4 w-4" />
                                    Image
                                </Button>
                                <Button
                                    variant={attachmentType === "document" ? "default" : "outline"}
                                    size="sm"
                                    onClick={() => setAttachmentType("document")}
                                >
                                    <Paperclip className="mr-2 h-4 w-4" />
                                    Doc
                                </Button>
                            </div>
                        </div>
                        <div className="space-y-2">
                            <label className="text-xs font-semibold uppercase text-gray-500">Media URL</label>
                            <Input
                                value={attachmentUrl}
                                onChange={(event) => setAttachmentUrl(event.target.value)}
                                placeholder="https://..."
                                disabled={disabled}
                            />
                        </div>
                    </div>
                    {attachmentUrl ? (
                        <div className="rounded-xl border border-dashed border-gray-200 bg-gray-50 p-3 text-xs text-gray-600">
                            {attachmentType === "image" ? (
                                <img
                                    src={attachmentUrl}
                                    alt={attachmentName || "preview"}
                                    className="max-h-40 rounded-lg object-cover"
                                />
                            ) : (
                                <div className="space-y-1">
                                    <div className="font-semibold">Document preview</div>
                                    <div>{attachmentName || attachmentUrl}</div>
                                </div>
                            )}
                        </div>
                    ) : null}
                    <div className="space-y-2">
                        <label className="text-xs font-semibold uppercase text-gray-500">Message</label>
                        <Textarea
                            placeholder="Type your message..."
                            value={message}
                            onChange={(e) => {
                                setMessage(e.target.value);
                                if (typingTimeout) {
                                    clearTimeout(typingTimeout);
                                }
                                if (e.target.value.trim()) {
                                    onTypingStart?.();
                                    const timeout = setTimeout(() => {
                                        onTypingStop?.();
                                    }, 1500);
                                    setTypingTimeout(timeout);
                                } else {
                                    onTypingStop?.();
                                }
                            }}
                            className="min-h-[44px] max-h-40"
                            disabled={disabled}
                            onKeyDown={(e) => {
                                if (e.key === "Enter" && !e.shiftKey) {
                                    e.preventDefault();
                                    handleSend();
                                }
                            }}
                        />
                    </div>
                </div>
            )}

            <div className="flex items-center justify-between px-4 pb-4">
                <p className="text-xs text-muted-foreground">
                    Tip: use template mode for approved WhatsApp templates.
                </p>
                <Button onClick={handleSend} disabled={disabled} className="gap-2">
                    <Send size={16} />
                    Send
                </Button>
            </div>
        </div>
    );
}
