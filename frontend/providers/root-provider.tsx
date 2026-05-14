"use client";

import React, { ReactNode } from "react";
import { AppThemeProvider } from "./theme-provider";
import { QueryProvider } from "./query-provider";
import { WebSocketProvider } from "@/websocket/provider";
import { Toaster } from "react-hot-toast";

interface RootProviderProps {
    children: ReactNode;
}

export function RootProvider({ children }: RootProviderProps) {
    return (
        <AppThemeProvider>
            <QueryProvider>
                <WebSocketProvider>
                    {children}
                    <Toaster position="top-right" />
                </WebSocketProvider>
            </QueryProvider>
        </AppThemeProvider>
    );
}
