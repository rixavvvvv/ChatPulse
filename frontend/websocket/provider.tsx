"use client";

import React, { createContext, useContext, useEffect, useRef, useState } from "react";
import { getSession, onSessionUpdated } from "@/lib/session";

type WebSocketListener = (data?: unknown) => void;
type WebSocketAnyListener = (event: string, data?: unknown) => void;

export interface WebSocketClient {
    connected: boolean;
    on: (event: string, listener: WebSocketListener) => void;
    off: (event: string, listener: WebSocketListener) => void;
    onAny: (listener: WebSocketAnyListener) => void;
    offAny: (listener: WebSocketAnyListener) => void;
    emit: (event: string, data?: unknown) => void;
    disconnect: () => void;
    connect: () => void;
}

interface WebSocketContextType {
    socket: WebSocketClient | null;
    isConnected: boolean;
    typingUsers: Set<string>;
    onlineUsers: Set<string>;
}

const WebSocketContext = createContext<WebSocketContextType | undefined>(undefined);

function normalizeSocketUrl(baseUrl: string, token: string): string {
    const normalized = baseUrl.trim().replace(/\/$/, "");
    const wsBase = normalized.replace(/^http/i, "ws");
    return `${wsBase}/ws?token=${encodeURIComponent(token)}`;
}

function createWebSocketClient(
    url: string,
    onConnected: (connected: boolean) => void,
    onMessage: (event: string, data: unknown) => void,
): WebSocketClient {
    let socket: WebSocket | null = null;
    let connected = false;
    const listeners = new Map<string, Set<WebSocketListener>>();
    const anyListeners = new Set<WebSocketAnyListener>();

    const notify = (event: string, data?: unknown) => {
        anyListeners.forEach((listener) => listener(event, data));
        const set = listeners.get(event);
        if (set) {
            set.forEach((listener) => listener(data));
        }
    };

    const handleEvent = (eventType: string, payload: unknown) => {
        notify(eventType, payload);

        const withUnderscores = eventType.replace(/\./g, "_");
        if (withUnderscores !== eventType) {
            notify(withUnderscores, payload);
        }

        if (eventType === "typing") {
            const data = payload as { is_typing?: boolean } | undefined;
            const derivedEvent = data?.is_typing ? "typing.start" : "typing.stop";
            notify(derivedEvent, payload);
            notify(derivedEvent.replace(/\./g, "_"), payload);
        }

        if (eventType === "unread.update") {
            notify("unread.updated", payload);
            notify("unread_updated", payload);
        }

        if (eventType === "presence.update") {
            const data = payload as { status?: string } | undefined;
            if (data?.status === "online") {
                notify("user_online", payload);
            }
            if (data?.status === "offline") {
                notify("user_offline", payload);
            }
        }
    };

    const connect = () => {
        if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) {
            return;
        }

        socket = new WebSocket(url);

        socket.addEventListener("open", () => {
            connected = true;
            onConnected(true);
            notify("connect");
        });

        socket.addEventListener("close", () => {
            connected = false;
            onConnected(false);
            notify("disconnect");
        });

        socket.addEventListener("message", (event) => {
            try {
                const parsed = JSON.parse(event.data as string) as {
                    event_type?: string;
                    payload?: unknown;
                };
                if (parsed?.event_type) {
                    handleEvent(parsed.event_type, parsed.payload ?? {});
                }
            } catch {
                // Ignore malformed messages.
            }
        });

        socket.addEventListener("error", () => {
            notify("connect_error");
        });
    };

    const emit = (event: string, data?: unknown) => {
        if (!socket || socket.readyState !== WebSocket.OPEN) {
            return;
        }

        let action = event;
        if (event === "typing.start") {
            action = "typing_start";
        } else if (event === "typing.stop") {
            action = "typing_stop";
        }

        socket.send(
            JSON.stringify({
                action,
                ...(data && typeof data === "object" ? data : {}),
            }),
        );
    };

    const disconnect = () => {
        socket?.close();
    };

    connect();

    return {
        get connected() {
            return connected;
        },
        on(event, listener) {
            if (!listeners.has(event)) {
                listeners.set(event, new Set());
            }
            listeners.get(event)?.add(listener);
        },
        off(event, listener) {
            listeners.get(event)?.delete(listener);
        },
        onAny(listener) {
            anyListeners.add(listener);
        },
        offAny(listener) {
            anyListeners.delete(listener);
        },
        emit,
        disconnect,
        connect,
    };
}

export function WebSocketProvider({ children }: { children: React.ReactNode }) {
    const [socket, setSocket] = useState<WebSocketClient | null>(null);
    const [isConnected, setIsConnected] = useState(false);
    const [typingUsers, setTypingUsers] = useState<Set<string>>(new Set());
    const [onlineUsers, setOnlineUsers] = useState<Set<string>>(new Set());
    const [token, setToken] = useState<string | null>(null);
    const reconnectTimer = useRef<number | null>(null);
    const reconnectAttempts = useRef(0);
    const shouldReconnect = useRef(true);

    useEffect(() => {
        const load = () => {
            const session = getSession();
            setToken(session?.access_token ?? null);
        };
        load();
        return onSessionUpdated(load);
    }, []);

    useEffect(() => {
        if (!token) return;

        const socketBaseUrl =
            process.env.NEXT_PUBLIC_SOCKET_URL ||
            process.env.NEXT_PUBLIC_API_URL ||
            "http://localhost:8000";

        shouldReconnect.current = true;
        reconnectAttempts.current = 0;

        const connect = () => {
            const url = normalizeSocketUrl(socketBaseUrl, token);
            const client = createWebSocketClient(
                url,
                (connected) => {
                    setIsConnected(connected);
                    if (!connected && shouldReconnect.current) {
                        if (reconnectAttempts.current < 5) {
                            reconnectAttempts.current += 1;
                            if (reconnectTimer.current) {
                                window.clearTimeout(reconnectTimer.current);
                            }
                            reconnectTimer.current = window.setTimeout(connect, 1000 * reconnectAttempts.current);
                        }
                    } else if (connected) {
                        reconnectAttempts.current = 0;
                    }
                },
                () => {
                    return;
                },
            );

            client.on("typing.start", (data: { user_id: string }) => {
                setTypingUsers((prev) => new Set(prev).add(data.user_id));
            });

            client.on("typing.stop", (data: { user_id: string }) => {
                setTypingUsers((prev) => {
                    const next = new Set(prev);
                    next.delete(data.user_id);
                    return next;
                });
            });

            client.on("user_online", (data: { user_id: string }) => {
                setOnlineUsers((prev) => new Set(prev).add(data.user_id));
            });

            client.on("user_offline", (data: { user_id: string }) => {
                setOnlineUsers((prev) => {
                    const next = new Set(prev);
                    next.delete(data.user_id);
                    return next;
                });
            });

            setSocket(client);
        };

        connect();

        return () => {
            shouldReconnect.current = false;
            if (reconnectTimer.current) {
                window.clearTimeout(reconnectTimer.current);
            }
            setSocket((current) => {
                current?.disconnect();
                return null;
            });
        };
    }, [token]);

    return (
        <WebSocketContext.Provider
            value={{
                socket,
                isConnected,
                typingUsers,
                onlineUsers,
            }}
        >
            {children}
        </WebSocketContext.Provider>
    );
}

export function useWebSocket() {
    const context = useContext(WebSocketContext);
    if (context === undefined) {
        throw new Error("useWebSocket must be used within WebSocketProvider");
    }
    return context;
}
