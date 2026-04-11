"use client";

import { FormEvent, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { apiRequest } from "@/lib/api";
import { getSession, saveSession } from "@/lib/session";

type OnboardingStatus = {
    user_id: number;
    workspace_id: number;
    workspace_name: string;
    workspace_created: boolean;
    meta_connected: boolean;
    subscription_active: boolean;
    ready: boolean;
};

type WorkspaceResponse = {
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

export default function OnboardingPage() {
    const [status, setStatus] = useState<OnboardingStatus | null>(null);
    const [workspaceName, setWorkspaceName] = useState("Growth Ops Workspace");
    const [phoneNumberId, setPhoneNumberId] = useState("");
    const [accessToken, setAccessToken] = useState("");
    const [businessAccountId, setBusinessAccountId] = useState("");
    const [loading, setLoading] = useState(true);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [success, setSuccess] = useState<string | null>(null);

    async function refreshStatus() {
        const session = getSession();
        if (!session) {
            setLoading(false);
            return;
        }

        try {
            const next = await apiRequest<OnboardingStatus>("/onboarding/status", {}, session.access_token);
            setStatus(next);
        } catch (err) {
            setError(err instanceof Error ? err.message : "Failed to load onboarding status");
        } finally {
            setLoading(false);
        }
    }

    useEffect(() => {
        void refreshStatus();
    }, []);

    async function handleCreateWorkspace(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        const session = getSession();
        if (!session) {
            return;
        }

        setBusy(true);
        setError(null);
        setSuccess(null);
        try {
            const workspace = await apiRequest<WorkspaceResponse>(
                "/workspaces",
                {
                    method: "POST",
                    body: JSON.stringify({ name: workspaceName }),
                },
                session.access_token,
            );

            const switched = await apiRequest<SwitchWorkspaceResponse>(
                "/workspaces/switch",
                {
                    method: "POST",
                    body: JSON.stringify({ workspace_id: workspace.id }),
                },
                session.access_token,
            );

            saveSession({
                access_token: switched.access_token,
                workspace_id: switched.workspace_id,
                role: switched.role,
            });
            setSuccess(`Workspace created and switched: ${workspace.name}`);
            await refreshStatus();
        } catch (err) {
            setError(err instanceof Error ? err.message : "Unable to create workspace");
        } finally {
            setBusy(false);
        }
    }

    async function handleConnectMeta(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        const session = getSession();
        if (!session) {
            return;
        }

        setBusy(true);
        setError(null);
        setSuccess(null);
        try {
            await apiRequest(
                "/meta/connect",
                {
                    method: "POST",
                    body: JSON.stringify({
                        phone_number_id: phoneNumberId,
                        access_token: accessToken,
                        business_account_id: businessAccountId,
                    }),
                },
                session.access_token,
            );
            setSuccess("Meta credentials connected successfully");
            await refreshStatus();
        } catch (err) {
            setError(err instanceof Error ? err.message : "Unable to connect Meta");
        } finally {
            setBusy(false);
        }
    }

    return (
        <div className="space-y-6">
            <section className="rounded-3xl border border-sky-100 bg-gradient-to-r from-amber-50 via-orange-50 to-cyan-50 p-8 shadow-soft">
                <p className="mb-2 text-xs font-semibold uppercase tracking-[0.22em] text-orange-700">Flow 1: User Onboarding</p>
                <h2 className="font-[var(--font-space-grotesk)] text-3xl font-semibold text-slate-900 md:text-4xl">
                    Workspace and Meta launch checklist
                </h2>
                <p className="mt-3 max-w-2xl text-slate-700">
                    Create or switch workspace, connect Meta credentials, and verify this workspace is ready to run campaigns.
                </p>
            </section>

            <section className="grid gap-4 md:grid-cols-3">
                <Card className={status?.workspace_created ? "border-emerald-200" : "border-slate-200"}>
                    <CardHeader>
                        <CardTitle>Workspace</CardTitle>
                        <CardDescription>{status?.workspace_name ?? "No active workspace"}</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <p className={status?.workspace_created ? "text-emerald-700" : "text-amber-700"}>
                            {status?.workspace_created ? "Ready" : "Pending"}
                        </p>
                    </CardContent>
                </Card>
                <Card className={status?.meta_connected ? "border-emerald-200" : "border-slate-200"}>
                    <CardHeader>
                        <CardTitle>Meta Connection</CardTitle>
                        <CardDescription>WhatsApp Cloud credentials</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <p className={status?.meta_connected ? "text-emerald-700" : "text-amber-700"}>
                            {status?.meta_connected ? "Connected" : "Pending"}
                        </p>
                    </CardContent>
                </Card>
                <Card className={status?.subscription_active ? "border-emerald-200" : "border-slate-200"}>
                    <CardHeader>
                        <CardTitle>Subscription</CardTitle>
                        <CardDescription>Billing status for message sending</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <p className={status?.subscription_active ? "text-emerald-700" : "text-amber-700"}>
                            {status?.subscription_active ? "Active" : "Inactive"}
                        </p>
                    </CardContent>
                </Card>
            </section>

            <div className="grid gap-6 lg:grid-cols-2">
                <Card>
                    <CardHeader>
                        <CardTitle>Create Workspace</CardTitle>
                        <CardDescription>Create a workspace and switch token context immediately.</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <form className="space-y-4" onSubmit={handleCreateWorkspace}>
                            <Input value={workspaceName} onChange={(event) => setWorkspaceName(event.target.value)} required />
                            <Button type="submit" disabled={busy || loading}>
                                {busy ? "Creating..." : "Create and Switch"}
                            </Button>
                        </form>
                    </CardContent>
                </Card>

                <Card>
                    <CardHeader>
                        <CardTitle>Connect Meta</CardTitle>
                        <CardDescription>Save workspace-scoped Meta credentials.</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <form className="space-y-3" onSubmit={handleConnectMeta}>
                            <Input
                                placeholder="Phone Number ID"
                                value={phoneNumberId}
                                onChange={(event) => setPhoneNumberId(event.target.value)}
                                required
                            />
                            <Input
                                placeholder="Business Account ID"
                                value={businessAccountId}
                                onChange={(event) => setBusinessAccountId(event.target.value)}
                                required
                            />
                            <Input
                                placeholder="Access Token"
                                value={accessToken}
                                onChange={(event) => setAccessToken(event.target.value)}
                                required
                            />
                            <Button type="submit" disabled={busy || loading}>
                                {busy ? "Saving..." : "Connect Meta"}
                            </Button>
                        </form>
                    </CardContent>
                </Card>
            </div>

            {loading ? <p className="text-sm text-slate-500">Checking onboarding status...</p> : null}
            {status && status.ready ? <p className="text-sm font-medium text-emerald-700">This workspace is ready for campaign execution.</p> : null}
            {success ? <p className="text-sm text-emerald-700">{success}</p> : null}
            {error ? <p className="text-sm text-rose-700">{error}</p> : null}
        </div>
    );
}
