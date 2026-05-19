"use client";

import { useEffect } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useWebSocket } from "@/websocket/provider";
import {
    connectMeta,
    disconnectMeta,
    getMetaConnection,
    getMetaWebhookDiagnostics,
    MetaWebhookDiagnostics,
    rotateMetaToken,
    subscribeWebhook,
    syncMetaTemplates,
    testWebhookVerifyToken,
    validateMeta,
    MetaConnectionResponse,
    MetaCredentialPayload,
} from "@/lib/services/meta";

const META_QUERY_KEY = ["meta", "connection"] as const;
const META_DIAGNOSTICS_QUERY_KEY = ["meta", "webhook-diagnostics"] as const;

export function useMetaConnection() {
    const { socket } = useWebSocket();
    const queryClient = useQueryClient();

    useEffect(() => {
        if (!socket) return;

        const handleUpdate = () => {
            queryClient.invalidateQueries({ queryKey: META_QUERY_KEY });
        };

        socket.on("meta.connection.updated", handleUpdate);
        socket.on("meta.connection_updated", handleUpdate);

        return () => {
            socket.off("meta.connection.updated", handleUpdate);
            socket.off("meta.connection_updated", handleUpdate);
        };
    }, [socket, queryClient]);

    return useQuery<MetaConnectionResponse>({
        queryKey: META_QUERY_KEY,
        queryFn: () => getMetaConnection(),
        refetchInterval: 30000,
    });
}

export function useMetaWebhookDiagnostics() {
    return useQuery<MetaWebhookDiagnostics>({
        queryKey: META_DIAGNOSTICS_QUERY_KEY,
        queryFn: () => getMetaWebhookDiagnostics(),
        refetchInterval: 30000,
    });
}

export function useMetaConnect() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (payload: MetaCredentialPayload) => connectMeta(payload),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: META_QUERY_KEY });
        },
    });
}

export function useMetaValidate() {
    return useMutation({
        mutationFn: (payload: MetaCredentialPayload) => validateMeta(payload),
    });
}

export function useMetaRotateToken() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (accessToken: string) => rotateMetaToken(accessToken),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: META_QUERY_KEY });
        },
    });
}

export function useMetaDisconnect() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: () => disconnectMeta(),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: META_QUERY_KEY });
        },
    });
}

export function useMetaWebhookSubscribe() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: () => subscribeWebhook(),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: META_QUERY_KEY });
        },
    });
}

export function useMetaWebhookTest() {
    return useMutation({
        mutationFn: (verifyToken: string) => testWebhookVerifyToken(verifyToken),
    });
}

export function useMetaSyncTemplates() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: () => syncMetaTemplates(),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: META_QUERY_KEY });
        },
    });
}
