import React, { useState } from "react";
import { Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

interface MessageComposerProps {
    onSend: (message: string) => void;
    disabled?: boolean;
    onTypingStart?: () => void;
    onTypingStop?: () => void;
}

export function MessageComposer({ onSend, disabled, onTypingStart, onTypingStop }: MessageComposerProps) {
    const [message, setMessage] = useState("");
    const [typingTimeout, setTypingTimeout] = useState<ReturnType<typeof setTimeout> | null>(null);

    const handleSend = () => {
        if (!message.trim()) return;
        onSend(message.trim());
        setMessage("");
    };

    return (
        <div className="p-4 border-t border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-950">
            <div className="flex items-end gap-3">
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
                <Button onClick={handleSend} disabled={disabled} className="gap-2">
                    <Send size={16} />
                    Send
                </Button>
            </div>
        </div>
    );
}
