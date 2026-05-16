"use client";

import { useRef, useCallback, useEffect } from "react";
import { Socket } from "socket.io-client";

export interface WebSocketEvent {
    id: string;
    type: "received" | "emitted";
    event: string;
    data: unknown;
    timestamp: number;
}

export interface WebSocketDebugState {
    isConnected: boolean;
    reconnectCount: number;
    activeRooms: Set<string>;
    receivedEvents: WebSocketEvent[];
    emittedEvents: WebSocketEvent[];
    latency: number;
    lastPing: number;
}

interface UseWebSocketDebugOptions {
    socket: Socket | null;
    enabled?: boolean;
}

export function useWebSocketDebug({ socket, enabled = true }: UseWebSocketDebugOptions) {
    const stateRef = useRef<WebSocketDebugState>({
        isConnected: false,
        reconnectCount: 0,
        activeRooms: new Set(),
        receivedEvents: [],
        emittedEvents: [],
        latency: 0,
        lastPing: 0,
    });

    const eventIdRef = useRef(0);

    const addEvent = useCallback((type: "received" | "emitted", event: string, data: unknown) => {
        if (!enabled) return;

        const newEvent: WebSocketEvent = {
            id: `evt_${Date.now()}_${eventIdRef.current++}`,
            type,
            event,
            data,
            timestamp: Date.now(),
        };

        const state = stateRef.current;

        if (type === "received") {
            state.receivedEvents = [...state.receivedEvents.slice(-99), newEvent];
        } else {
            state.emittedEvents = [...state.emittedEvents.slice(-99), newEvent];
        }
    }, [enabled]);

    const emit = useCallback((event: string, data?: unknown) => {
        if (!socket || !enabled) return null;

        addEvent("emitted", event, data);
        return socket.emit(event, data);
    }, [socket, enabled, addEvent]);

    useEffect(() => {
        if (!socket || !enabled) return;

        const onConnect = () => {
            stateRef.current.isConnected = true;
            stateRef.current.lastPing = Date.now();
        };

        const onDisconnect = () => {
            stateRef.current.isConnected = false;
        };

        const onReconnect = () => {
            stateRef.current.reconnectCount++;
            stateRef.current.lastPing = Date.now();
        };

        const onPing = () => {
            const now = Date.now();
            stateRef.current.latency = now - stateRef.current.lastPing;
            stateRef.current.lastPing = now;
        };

        const handleAnyEvent = (event: string, data: unknown) => {
            if (event !== "ping" && event !== "connect" && event !== "disconnect" &&
                event !== "reconnect" && event !== "reconnect_attempt" && event !== "connect_error") {
                addEvent("received", event, data);
            }
        };

        socket.on("connect", onConnect);
        socket.on("disconnect", onDisconnect);
        socket.on("reconnect", onReconnect);
        socket.on("ping", onPing);

        socket.onAny(handleAnyEvent);

        stateRef.current.isConnected = socket.connected;
        stateRef.current.reconnectCount = 0;

        return () => {
            socket.off("connect", onConnect);
            socket.off("disconnect", onDisconnect);
            socket.off("reconnect", onReconnect);
            socket.off("ping", onPing);
            socket.offAny(handleAnyEvent);
        };
    }, [socket, enabled, addEvent]);

    const reconnect = useCallback(() => {
        if (socket) {
            socket.disconnect();
            socket.connect();
        }
    }, [socket]);

    const simulateDisconnect = useCallback(() => {
        if (socket) {
            socket.disconnect();
        }
    }, [socket]);

    const clearEvents = useCallback(() => {
        stateRef.current.receivedEvents = [];
        stateRef.current.emittedEvents = [];
    }, []);

    const getState = useCallback((): WebSocketDebugState => {
        const state = stateRef.current;
        return {
            ...state,
            activeRooms: new Set(state.activeRooms),
            receivedEvents: [...state.receivedEvents],
            emittedEvents: [...state.emittedEvents],
        };
    }, []);

    return {
        emit,
        reconnect,
        simulateDisconnect,
        clearEvents,
        getState,
    };
}