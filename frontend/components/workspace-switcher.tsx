"use client";

import { useEffect, useMemo, useState } from "react";

import { apiRequest } from "@/lib/api";
import { getSession, onSessionUpdated, saveSession } from "@/lib/session";

type WorkspaceItem = {
    id: number;
    name: string;
    owner_id: number;
    role: string;
    created_at: string;
};

type SwitchWorkspaceResponse = {
    access_token: string;
    token_type: string;
    workspace_id: number;
    role: string;
};

export function WorkspaceSwitcher() {
    const [workspaces, setWorkspaces] = useState<WorkspaceItem[]>([]);
    const [currentWorkspaceId, setCurrentWorkspaceId] = useState<number | null>(null);
    const [loading, setLoading] = useState(true);
    const [switching, setSwitching] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const currentWorkspace = useMemo(
        () => workspaces.find((workspace) => workspace.id === currentWorkspaceId),
        [workspaces, currentWorkspaceId],
    );

    useEffect(() => {
        const refresh = async () => {
            const session = getSession();
            if (!session) {
                setLoading(false);
                return;
            }

            setCurrentWorkspaceId(session.workspace_id);
            setError(null);
            try {
                const items = await apiRequest<WorkspaceItem[]>("/workspaces", {}, session.access_token);
                setWorkspaces(items);
            } catch (err) {
                setError(err instanceof Error ? err.message : "Failed to load workspaces");
            } finally {
                setLoading(false);
            }
        };

        void refresh();
        return onSessionUpdated(() => {
            void refresh();
        });
    }, []);

    async function handleWorkspaceChange(nextWorkspaceId: number) {
        const session = getSession();
        if (!session || nextWorkspaceId === session.workspace_id) {
            return;
        }

        setSwitching(true);
        setError(null);
        try {
            const switched = await apiRequest<SwitchWorkspaceResponse>(
                "/workspaces/switch",
                {
                    method: "POST",
                    body: JSON.stringify({ workspace_id: nextWorkspaceId }),
                },
                session.access_token,
            );

            saveSession({
                access_token: switched.access_token,
                workspace_id: switched.workspace_id,
                role: switched.role,
            });
            setCurrentWorkspaceId(switched.workspace_id);
            window.location.reload();
        } catch (err) {
            setError(err instanceof Error ? err.message : "Failed to switch workspace");
        } finally {
            setSwitching(false);
        }
    }

    if (loading) {
        return <p className="text-xs text-slate-500">Loading workspace...</p>;
    }

    if (workspaces.length === 0) {
        return <p className="text-xs text-amber-700">No workspaces available</p>;
    }

    return (
        <div className="space-y-1">
            <label htmlFor="workspace-switcher" className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">
                Workspace
            </label>
            <div className="flex items-center gap-2">
                <select
                    id="workspace-switcher"
                    value={currentWorkspaceId ?? undefined}
                    onChange={(event) => {
                        const nextWorkspaceId = Number(event.target.value);
                        if (Number.isFinite(nextWorkspaceId)) {
                            void handleWorkspaceChange(nextWorkspaceId);
                        }
                    }}
                    className="min-w-48 rounded-lg border border-border bg-white px-3 py-2 text-sm text-slate-900 outline-none ring-offset-background focus-visible:ring-2 focus-visible:ring-ring"
                    disabled={switching}
                >
                    {workspaces.map((workspace) => (
                        <option key={workspace.id} value={workspace.id}>
                            {workspace.name}
                        </option>
                    ))}
                </select>
                {switching ? <span className="text-xs text-slate-500">Switching...</span> : null}
            </div>
            {currentWorkspace ? <p className="text-xs text-slate-500">Role: {currentWorkspace.role}</p> : null}
            {error ? <p className="text-xs text-rose-700">{error}</p> : null}
        </div>
    );
}
