"use client";

import { useEffect, useState, useRef } from "react";
import { format } from "date-fns";
import { Search, Send, User } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
    listConversations,
    getConversationMessages,
    sendConversationMessage,
    markConversationRead,
    Conversation,
    ConversationMessage,
} from "@/lib/services/conversations";
import { getSession } from "@/lib/session";
import { getApiUrl } from "@/lib/api";

export default function ChatsPage() {
    const [conversations, setConversations] = useState<Conversation[]>([]);
    const [selectedConvId, setSelectedConvId] = useState<number | null>(null);
    const [messages, setMessages] = useState<ConversationMessage[]>([]);
    const [inputText, setInputText] = useState("");
    const [isLoading, setIsLoading] = useState(true);
    
    const messagesEndRef = useRef<HTMLDivElement>(null);
    const wsRef = useRef<WebSocket | null>(null);

    // Fetch initial conversations
    useEffect(() => {
        listConversations()
            .then(data => {
                setConversations(data);
                setIsLoading(false);
            })
            .catch(console.error);
    }, []);

    // WebSocket connection
    useEffect(() => {
        const session = getSession();
        if (!session) return;

        // Build WS URL. If getApiUrl returns http://..., convert to ws://...
        const apiUrl = getApiUrl("");
        const wsUrl = apiUrl.replace(/^http/, "ws") + `/ws?token=${session.access_token}`;
        
        const ws = new WebSocket(wsUrl);
        wsRef.current = ws;

        ws.onopen = () => {
            console.log("WebSocket connected");
        };

        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                if (data.event_type === "message.created") {
                    const msg = data.message as ConversationMessage;
                    const convId = data.conversation_id as number;

                    // Update messages if we are viewing this conversation
                    setMessages(prev => {
                        // Only add if we're in the right conversation and it's not already there
                        if (selectedConvId === convId && !prev.find(m => m.id === msg.id)) {
                            return [...prev, msg];
                        }
                        return prev;
                    });

                    // Update conversations list (move to top, update preview/unread)
                    setConversations(prev => {
                        const existing = prev.find(c => c.id === convId);
                        if (!existing) {
                            // If it's a new conversation, we should probably fetch it, but for now we just reload list
                            listConversations().then(setConversations);
                            return prev;
                        }

                        const updated = {
                            ...existing,
                            last_message_preview: msg.content,
                            last_message_at: msg.created_at,
                            unread_count: selectedConvId === convId ? 0 : existing.unread_count + 1
                        };

                        const others = prev.filter(c => c.id !== convId);
                        return [updated, ...others];
                    });

                    // Auto-read if we are looking at it
                    if (selectedConvId === convId) {
                        markConversationRead(convId).catch(console.error);
                    }
                }
            } catch (err) {
                console.error("Failed to parse WS message", err);
            }
        };

        return () => {
            ws.close();
        };
    }, [selectedConvId]);

    // Fetch messages when conversation selected
    useEffect(() => {
        if (!selectedConvId) {
            setMessages([]);
            return;
        }

        getConversationMessages(selectedConvId)
            .then(data => {
                setMessages(data);
                // Mark read
                markConversationRead(selectedConvId).then(() => {
                    setConversations(prev => prev.map(c => 
                        c.id === selectedConvId ? { ...c, unread_count: 0 } : c
                    ));
                });
            })
            .catch(console.error);

        // Join room
        if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
            wsRef.current.send(JSON.stringify({ action: "join_conversation", conversation_id: selectedConvId }));
        }

    }, [selectedConvId]);

    // Scroll to bottom when messages change
    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [messages]);

    const handleSend = async () => {
        if (!inputText.trim() || !selectedConvId) return;

        const text = inputText;
        setInputText("");

        try {
            const newMsg = await sendConversationMessage(selectedConvId, text);
            setMessages(prev => {
                if (prev.find(m => m.id === newMsg.id)) return prev;
                return [...prev, newMsg];
            });
            
            setConversations(prev => {
                const existing = prev.find(c => c.id === selectedConvId);
                if (!existing) return prev;
                const updated = {
                    ...existing,
                    last_message_preview: text,
                    last_message_at: newMsg.created_at
                };
                return [updated, ...prev.filter(c => c.id !== selectedConvId)];
            });
        } catch (err) {
            console.error("Failed to send message", err);
            // Revert input text on failure
            setInputText(text);
        }
    };

    const selectedConv = conversations.find(c => c.id === selectedConvId);

    return (
        <div className="flex h-[calc(100vh-2rem)] w-full overflow-hidden rounded-xl border border-border bg-white shadow-sm">
            {/* Sidebar */}
            <div className="flex w-80 flex-col border-r border-border bg-slate-50/50">
                <div className="p-4 pb-2">
                    <h2 className="text-lg font-semibold text-slate-900">Inbox</h2>
                </div>
                <div className="px-4 pb-4">
                    <div className="relative">
                        <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-slate-400" />
                        <Input placeholder="Search chats..." className="pl-9 bg-white" />
                    </div>
                </div>
                
                <div className="flex-1 overflow-y-auto">
                    {isLoading ? (
                        <div className="p-4 text-center text-sm text-slate-500">Loading chats...</div>
                    ) : conversations.length === 0 ? (
                        <div className="p-4 text-center text-sm text-slate-500">No conversations yet.</div>
                    ) : (
                        <div className="space-y-1 p-2">
                            {conversations.map(conv => (
                                <button
                                    key={conv.id}
                                    onClick={() => setSelectedConvId(conv.id)}
                                    className={`flex w-full items-start gap-3 rounded-lg p-3 text-left transition-colors ${
                                        selectedConvId === conv.id ? "bg-sky-100" : "hover:bg-slate-100"
                                    }`}
                                >
                                    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-slate-200 text-slate-500">
                                        <User className="h-5 w-5" />
                                    </div>
                                    <div className="flex-1 overflow-hidden">
                                        <div className="flex items-center justify-between">
                                            <span className="font-medium text-slate-900 truncate">
                                                +{conv.subject || conv.contact_id}
                                            </span>
                                            {conv.last_message_at && (
                                                <span className="text-xs text-slate-500">
                                                    {format(new Date(conv.last_message_at), "HH:mm")}
                                                </span>
                                            )}
                                        </div>
                                        <div className="flex items-center justify-between gap-2 mt-0.5">
                                            <span className="truncate text-sm text-slate-500">
                                                {conv.last_message_preview || "No messages"}
                                            </span>
                                            {conv.unread_count > 0 && (
                                                <span className="flex h-5 w-5 items-center justify-center rounded-full bg-sky-500 text-[10px] font-bold text-white">
                                                    {conv.unread_count}
                                                </span>
                                            )}
                                        </div>
                                    </div>
                                </button>
                            ))}
                        </div>
                    )}
                </div>
            </div>

            {/* Main Chat Area */}
            {selectedConvId && selectedConv ? (
                <div className="flex flex-1 flex-col bg-white">
                    {/* Header */}
                    <div className="flex items-center border-b border-border px-6 py-4">
                        <div className="flex h-10 w-10 items-center justify-center rounded-full bg-slate-100 text-slate-500">
                            <User className="h-5 w-5" />
                        </div>
                        <div className="ml-4">
                            <h3 className="font-semibold text-slate-900">+{selectedConv.subject || selectedConv.contact_id}</h3>
                            <p className="text-xs text-slate-500">Via {selectedConv.channel}</p>
                        </div>
                    </div>

                    {/* Messages */}
                    <div className="flex-1 overflow-y-auto p-6 bg-[url('/bg-pattern.png')] bg-repeat bg-[length:400px]">
                        <div className="space-y-4">
                            {messages.map(msg => {
                                const isInbound = msg.direction === "inbound";
                                return (
                                    <div key={msg.id} className={`flex ${isInbound ? "justify-start" : "justify-end"}`}>
                                        <div 
                                            className={`max-w-[75%] rounded-2xl px-4 py-2 ${
                                                isInbound 
                                                    ? "bg-white text-slate-900 border border-slate-200" 
                                                    : "bg-sky-500 text-white"
                                            }`}
                                        >
                                            <p className="whitespace-pre-wrap text-sm">{msg.content}</p>
                                            <p className={`mt-1 text-right text-[10px] ${isInbound ? "text-slate-400" : "text-sky-100"}`}>
                                                {format(new Date(msg.created_at), "HH:mm")}
                                            </p>
                                        </div>
                                    </div>
                                );
                            })}
                            <div ref={messagesEndRef} />
                        </div>
                    </div>

                    {/* Input */}
                    <div className="border-t border-border bg-white p-4">
                        <div className="flex items-end gap-2">
                            <Textarea 
                                placeholder="Type a message..." 
                                className="min-h-[2.5rem] flex-1 resize-none bg-slate-50 border-slate-200 py-3"
                                rows={1}
                                value={inputText}
                                onChange={e => setInputText(e.target.value)}
                                onKeyDown={e => {
                                    if (e.key === "Enter" && !e.shiftKey) {
                                        e.preventDefault();
                                        handleSend();
                                    }
                                }}
                            />
                            <Button 
                                size="icon" 
                                onClick={handleSend}
                                disabled={!inputText.trim()}
                                className="h-[3.25rem] w-[3.25rem] rounded-xl shrink-0"
                            >
                                <Send className="h-5 w-5" />
                            </Button>
                        </div>
                        <p className="mt-2 text-xs text-slate-400 text-center">
                            Press Enter to send. Shift+Enter for new line. Standard 24h Meta messaging window applies.
                        </p>
                    </div>
                </div>
            ) : (
                <div className="flex flex-1 items-center justify-center bg-slate-50/50">
                    <div className="text-center">
                        <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-slate-100">
                            <Send className="h-8 w-8 text-slate-400" />
                        </div>
                        <h3 className="mt-4 text-lg font-medium text-slate-900">Your Inbox</h3>
                        <p className="mt-1 text-sm text-slate-500">Select a conversation to start messaging</p>
                    </div>
                </div>
            )}
        </div>
    );
}
