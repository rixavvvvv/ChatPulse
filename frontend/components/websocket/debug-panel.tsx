"use client";

import React, { useState, useEffect, useRef } from "react";
import { useWebSocket } from "@/websocket/provider";
import { useWebSocketDebug, WebSocketEvent } from "@/websocket/debug-hook";

export function WebSocketDebugPanel() {
    if (process.env.NODE_ENV !== "development") {
        return null;
    }

    return <DebugPanelInner />;
}

function DebugPanelInner() {
    const { socket, isConnected } = useWebSocket();
    const { emit: _emit, reconnect, simulateDisconnect, clearEvents, getState } = useWebSocketDebug({
        socket,
        enabled: true,
    });

    const [state, setState] = useState(() => getState());
    const [activeTab, setActiveTab] = useState<"received" | "emitted">("received");
    const [isExpanded, setIsExpanded] = useState(false);
    const [filter, setFilter] = useState("");
    const logEndRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        const interval = setInterval(() => {
            setState(getState());
        }, 500);
        return () => clearInterval(interval);
    }, [getState]);

    useEffect(() => {
        if (logEndRef.current && isExpanded) {
            logEndRef.current.scrollIntoView({ behavior: "smooth" });
        }
    }, [state.receivedEvents, state.emittedEvents, isExpanded]);

    const events = activeTab === "received" ? state.receivedEvents : state.emittedEvents;
    const filteredEvents = filter
        ? events.filter((e) => e.event.toLowerCase().includes(filter.toLowerCase()))
        : events;

    const formatTime = (timestamp: number) => {
        return new Date(timestamp).toLocaleTimeString("en-US", {
            hour12: false,
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
        });
    };

    const renderEvent = (evt: WebSocketEvent) => (
        <div
            key={evt.id}
            className={`text-xs py-1 px-2 border-b border-gray-700 ${
                evt.type === "received" ? "bg-blue-900/20" : "bg-orange-900/20"
            }`}
        >
            <div className="flex justify-between items-center">
                <span className={`font-mono font-semibold ${evt.type === "received" ? "text-blue-400" : "text-orange-400"}`}>
                    {evt.event}
                </span>
                <span className="text-gray-500">{formatTime(evt.timestamp)}</span>
            </div>
            {evt.data && (
                <pre className="text-gray-400 mt-1 text-[10px] overflow-x-auto whitespace-pre-wrap">
                    {JSON.stringify(evt.data, null, 1)}
                </pre>
            )}
        </div>
    );

    if (!isExpanded) {
        return (
            <div
                className="fixed bottom-4 right-4 z-50 bg-gray-900 border border-gray-700 rounded-lg shadow-lg cursor-pointer hover:border-gray-500 transition-colors"
                onClick={() => setIsExpanded(true)}
            >
                <div className="flex items-center gap-2 px-3 py-2">
                    <div className={`w-2 h-2 rounded-full ${isConnected ? "bg-green-500" : "bg-red-500"}`} />
                    <span className="text-xs font-mono text-gray-300">WS Debug</span>
                    {state.reconnectCount > 0 && (
                        <span className="text-[10px] text-yellow-500">({state.reconnectCount} reconn)</span>
                    )}
                    <span className="text-[10px] text-gray-500">
                        {state.latency > 0 ? `${state.latency}ms` : "--"}
                    </span>
                </div>
            </div>
        );
    }

    return (
        <div className="fixed bottom-4 right-4 z-50 w-96 bg-gray-900 border border-gray-700 rounded-lg shadow-lg">
            <div className="flex items-center justify-between px-3 py-2 border-b border-gray-700 bg-gray-800 rounded-t-lg">
                <div className="flex items-center gap-2">
                    <div className={`w-2 h-2 rounded-full ${isConnected ? "bg-green-500" : "bg-red-500"}`} />
                    <span className="text-xs font-mono text-gray-300">WebSocket Debug</span>
                </div>
                <button
                    onClick={() => setIsExpanded(false)}
                    className="text-gray-500 hover:text-gray-300 text-lg leading-none"
                >
                    ×
                </button>
            </div>

            <div className="grid grid-cols-4 gap-1 p-2 text-[10px] bg-gray-800/50">
                <div className="text-center">
                    <div className="text-gray-500">Status</div>
                    <div className={isConnected ? "text-green-400" : "text-red-400"}>
                        {isConnected ? "Connected" : "Disconnected"}
                    </div>
                </div>
                <div className="text-center">
                    <div className="text-gray-500">Reconnects</div>
                    <div className="text-yellow-400">{state.reconnectCount}</div>
                </div>
                <div className="text-center">
                    <div className="text-gray-500">Latency</div>
                    <div className={state.latency < 100 ? "text-green-400" : state.latency < 300 ? "text-yellow-400" : "text-red-400"}>
                        {state.latency > 0 ? `${state.latency}ms` : "--"}
                    </div>
                </div>
                <div className="text-center">
                    <div className="text-gray-500">Events</div>
                    <div className="text-blue-400">{state.receivedEvents.length + state.emittedEvents.length}</div>
                </div>
            </div>

            <div className="flex gap-1 p-2 border-b border-gray-700">
                <button
                    onClick={reconnect}
                    className="px-2 py-1 text-[10px] bg-green-700 hover:bg-green-600 rounded text-gray-200"
                >
                    Reconnect
                </button>
                <button
                    onClick={simulateDisconnect}
                    className="px-2 py-1 text-[10px] bg-yellow-700 hover:bg-yellow-600 rounded text-gray-200"
                >
                    Simulate Disconnect
                </button>
                <button
                    onClick={clearEvents}
                    className="px-2 py-1 text-[10px] bg-gray-700 hover:bg-gray-600 rounded text-gray-200"
                >
                    Clear
                </button>
            </div>

            <div className="flex border-b border-gray-700">
                <button
                    onClick={() => setActiveTab("received")}
                    className={`flex-1 py-1 text-[10px] ${activeTab === "received" ? "bg-blue-900/50 text-blue-400" : "text-gray-500 hover:text-gray-400"}`}
                >
                    Received ({state.receivedEvents.length})
                </button>
                <button
                    onClick={() => setActiveTab("emitted")}
                    className={`flex-1 py-1 text-[10px] ${activeTab === "emitted" ? "bg-orange-900/50 text-orange-400" : "text-gray-500 hover:text-gray-400"}`}
                >
                    Emitted ({state.emittedEvents.length})
                </button>
            </div>

            <div className="p-2 border-b border-gray-700">
                <input
                    type="text"
                    placeholder="Filter events..."
                    value={filter}
                    onChange={(e) => setFilter(e.target.value)}
                    className="w-full px-2 py-1 text-xs bg-gray-800 border border-gray-700 rounded text-gray-300 placeholder-gray-600 focus:border-gray-500 focus:outline-none"
                />
            </div>

            <div className="h-48 overflow-y-auto font-mono">
                {filteredEvents.length === 0 ? (
                    <div className="p-4 text-center text-gray-600 text-xs">No events yet</div>
                ) : (
                    filteredEvents.map(renderEvent)
                )}
                <div ref={logEndRef} />
            </div>
        </div>
    );
}