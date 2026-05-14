"use client";

import React, { createContext, useContext, useEffect, useState } from "react";
import { io, Socket } from "socket.io-client";
import { useAuthStore } from "@/stores/auth";

interface WebSocketContextType {
    socket: Socket | null;
    isConnected: boolean;
    typingUsers: Set<string>;
    onlineUsers: Set<string>;
}

const WebSocketContext = createContext<WebSocketContextType | undefined>(undefined);

export function WebSocketProvider({ children }: { children: React.ReactNode }) {
    const [socket, setSocket] = useState<Socket | null>(null);
    const [isConnected, setIsConnected] = useState(false);
    const [typingUsers, setTypingUsers] = useState<Set<string>>(new Set());
    const [onlineUsers, setOnlineUsers] = useState<Set<string>>(new Set());
    const { user } = useAuthStore();

    useEffect(() => {
        if (!user?.id) return;

        const token = localStorage.getItem("token");
        if (!token) return;

        const socketUrl = process.env.NEXT_PUBLIC_SOCKET_URL || "http://localhost:8000";
        const newSocket = io(socketUrl, {
            auth: { token },
            reconnection: true,
            reconnectionDelay: 1000,
            reconnectionDelayMax: 5000,
            reconnectionAttempts: 5,
        });

        newSocket.on("connect", () => {
            setIsConnected(true);
        });

        newSocket.on("disconnect", () => {
            setIsConnected(false);
        });

        newSocket.on("typing_start", (data: { user_id: string }) => {
            setTypingUsers((prev) => new Set(prev).add(data.user_id));
        });

        newSocket.on("typing_stop", (data: { user_id: string }) => {
            setTypingUsers((prev) => {
                const next = new Set(prev);
                next.delete(data.user_id);
                return next;
            });
        });

        newSocket.on("user_online", (data: { user_id: string }) => {
            setOnlineUsers((prev) => new Set(prev).add(data.user_id));
        });

        newSocket.on("user_offline", (data: { user_id: string }) => {
            setOnlineUsers((prev) => {
                const next = new Set(prev);
                next.delete(data.user_id);
                return next;
            });
        });

        setSocket(newSocket);

        return () => {
            newSocket.disconnect();
        };
    }, [user?.id]);

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
