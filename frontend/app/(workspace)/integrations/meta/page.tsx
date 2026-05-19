"use client";

import { useMemo, useState } from "react";
import toast from "react-hot-toast";
import { RefreshCw, ShieldCheck, Link2, Phone, KeyRound, Unplug, PlugZap } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { MetaCredentialForm } from "@/components/meta/credential-form";
import { MetaHealthIndicator } from "@/components/meta/health-indicator";
import { MetaStatusCard } from "@/components/meta/status-card";
import { MetaVerificationModal } from "@/components/meta/verification-modal";
import {
    useMetaConnection,
    useMetaConnect,
    useMetaDisconnect,
    useMetaRotateToken,
    useMetaSyncTemplates,
    useMetaValidate,
    useMetaWebhookSubscribe,
    useMetaWebhookDiagnostics,
    useMetaWebhookTest,
} from "@/hooks/useMetaConnection";

export default function MetaIntegrationPage() {
    const [rotateToken, setRotateToken] = useState("");
    const [testModalOpen, setTestModalOpen] = useState(false);

    const metaQuery = useMetaConnection();
    const connectMutation = useMetaConnect();
    const validateMutation = useMetaValidate();
    const disconnectMutation = useMetaDisconnect();
    const rotateMutation = useMetaRotateToken();
    const subscribeMutation = useMetaWebhookSubscribe();
    const webhookTestMutation = useMetaWebhookTest();
    const syncMutation = useMetaSyncTemplates();
    const diagnosticsQuery = useMetaWebhookDiagnostics();

    const credentials = metaQuery.data?.credentials;
    const phoneNumbers = metaQuery.data?.phone_numbers ?? [];
    const waba = metaQuery.data?.waba;
    const webhook = metaQuery.data?.webhook;
    const tokenStatus = metaQuery.data?.token_status;
    const health = metaQuery.data?.health;
    const diagnostics = diagnosticsQuery.data;

    const healthStatus = useMemo(() => {
        if (!credentials?.is_connected) return "disconnected";
        return health?.status ?? "healthy";
    }, [credentials?.is_connected, health?.status]);

    async function handleConnect(payload: any) {
        try {
            await connectMutation.mutateAsync(payload);
            toast.success("Meta credentials saved");
        } catch (err) {
            toast.error(err instanceof Error ? err.message : "Failed to save credentials");
        }
    }

    async function handleValidate(payload: any) {
        try {
            await validateMutation.mutateAsync(payload);
            toast.success("Credentials validated");
        } catch (err) {
            toast.error(err instanceof Error ? err.message : "Validation failed");
        }
    }

    async function handleRotateToken() {
        try {
            await rotateMutation.mutateAsync(rotateToken.trim());
            setRotateToken("");
            toast.success("Token rotated");
        } catch (err) {
            toast.error(err instanceof Error ? err.message : "Token rotation failed");
        }
    }

    async function handleDisconnect() {
        if (!confirm("Disconnect Meta credentials for this workspace?")) return;
        try {
            await disconnectMutation.mutateAsync();
            toast.success("Disconnected");
        } catch (err) {
            toast.error(err instanceof Error ? err.message : "Disconnect failed");
        }
    }

    async function handleWebhookSubscribe() {
        try {
            await subscribeMutation.mutateAsync();
            toast.success("Webhook subscription checked");
        } catch (err) {
            toast.error(err instanceof Error ? err.message : "Webhook subscribe failed");
        }
    }

    async function handleWebhookTest(token: string) {
        try {
            const result = await webhookTestMutation.mutateAsync(token);
            setTestModalOpen(false);
            if (result.ok) {
                toast.success("Webhook verify token matched");
            } else {
                toast.error(result.reason || "Webhook verify token mismatch");
            }
        } catch (err) {
            toast.error(err instanceof Error ? err.message : "Webhook test failed");
        }
    }

    async function handleSyncTemplates() {
        try {
            const result = await syncMutation.mutateAsync();
            toast.success(`Templates synced: ${result.created} created, ${result.updated} updated`);
        } catch (err) {
            toast.error(err instanceof Error ? err.message : "Template sync failed");
        }
    }

    return (
        <div className="space-y-6">
            <section className="rounded-3xl border border-border/80 bg-white/85 p-6 shadow-soft">
                <p className="text-xs font-semibold uppercase tracking-[0.22em] text-sky-700">Integrations</p>
                <h2 className="mt-2 flex items-center gap-2 font-[var(--font-space-grotesk)] text-3xl font-semibold text-slate-900">
                    <Phone className="h-8 w-8 text-sky-700" />
                    WhatsApp Connections
                </h2>
                <p className="mt-2 text-sm text-muted-foreground">
                    Connect your Meta WhatsApp Business account, manage credentials, and monitor account health in one place.
                </p>
            </section>

            <div className="flex flex-wrap items-center gap-3">
                <MetaHealthIndicator status={healthStatus} />
                <Button variant="outline" onClick={() => metaQuery.refetch()} disabled={metaQuery.isFetching}>
                    <RefreshCw className={metaQuery.isFetching ? "mr-2 h-4 w-4 animate-spin" : "mr-2 h-4 w-4"} />
                    Refresh
                </Button>
                <Button variant="outline" onClick={handleWebhookSubscribe} disabled={subscribeMutation.isPending}>
                    <Link2 className="mr-2 h-4 w-4" />
                    Subscribe Webhook
                </Button>
                <Button variant="outline" onClick={() => setTestModalOpen(true)}>
                    <ShieldCheck className="mr-2 h-4 w-4" />
                    Test Verify Token
                </Button>
                <Button variant="outline" onClick={handleSyncTemplates} disabled={syncMutation.isPending}>
                    <PlugZap className="mr-2 h-4 w-4" />
                    Sync Templates
                </Button>
                {credentials?.is_connected ? (
                    <Button variant="destructive" onClick={handleDisconnect} disabled={disconnectMutation.isPending}>
                        <Unplug className="mr-2 h-4 w-4" />
                        Disconnect
                    </Button>
                ) : null}
            </div>

            {metaQuery.isLoading ? (
                <Card>
                    <CardContent className="py-8 text-sm text-slate-500">Loading connection details...</CardContent>
                </Card>
            ) : metaQuery.error ? (
                <Card>
                    <CardContent className="py-8 text-sm text-rose-600">
                        {(metaQuery.error as Error).message}
                    </CardContent>
                </Card>
            ) : null}

            <div className="grid gap-6 lg:grid-cols-[1.2fr_1fr]">
                <MetaCredentialForm
                    initialValues={{
                        phone_number_id: credentials?.phone_number_id ?? "",
                        business_account_id: credentials?.business_account_id ?? "",
                    }}
                    onValidate={handleValidate}
                    onSubmit={handleConnect}
                    loading={connectMutation.isPending || validateMutation.isPending}
                />

                <Card>
                    <CardHeader>
                        <CardTitle>Credential Rotation</CardTitle>
                        <CardDescription>
                            Replace the access token without changing your phone number or WABA.
                        </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-3">
                        <Input
                            type="password"
                            placeholder="New access token"
                            value={rotateToken}
                            onChange={(event) => setRotateToken(event.target.value)}
                        />
                        <Button
                            onClick={handleRotateToken}
                            disabled={rotateMutation.isPending || !rotateToken.trim()}
                        >
                            <KeyRound className="mr-2 h-4 w-4" />
                            Rotate token
                        </Button>
                        <p className="text-xs text-muted-foreground">
                            Current token ends with: {credentials?.access_token_last4 || "----"}
                        </p>
                    </CardContent>
                </Card>
            </div>

            <div className="grid gap-6 lg:grid-cols-3">
                <MetaStatusCard title="Token Status" description="Live access token validation">
                    <div className="text-sm">
                        {tokenStatus?.is_valid ? "Valid" : "Invalid"}
                    </div>
                    {tokenStatus?.subject_name ? (
                        <div className="text-xs text-muted-foreground">{tokenStatus.subject_name}</div>
                    ) : null}
                    {tokenStatus?.error ? (
                        <div className="text-xs text-rose-600">{tokenStatus.error}</div>
                    ) : null}
                </MetaStatusCard>

                <MetaStatusCard title="Webhook" description="Meta callback & signature status">
                    <div className="text-sm">Verify token: {webhook?.verify_token_configured ? "Configured" : "Missing"}</div>
                    <div className="text-sm">Signature validation: {webhook?.signature_validation_enabled ? "On" : "Off"}</div>
                    {webhook?.callback_url ? (
                        <div className="text-xs text-muted-foreground break-all">{webhook.callback_url}</div>
                    ) : null}
                </MetaStatusCard>

                <MetaStatusCard title="WABA" description="Business account overview">
                    <div className="text-sm">{waba?.name || "Unknown"}</div>
                    <div className="text-xs text-muted-foreground">Status: {waba?.health_status || "n/a"}</div>
                    <div className="text-xs text-muted-foreground">Review: {waba?.account_review_status || "n/a"}</div>
                </MetaStatusCard>
            </div>

            <MetaStatusCard title="Webhook Diagnostics" description="Verification and signature resolution">
                {diagnosticsQuery.isLoading ? (
                    <div className="text-xs text-muted-foreground">Loading diagnostics...</div>
                ) : diagnosticsQuery.error ? (
                    <div className="text-xs text-rose-600">Unable to load diagnostics</div>
                ) : (
                    <div className="space-y-1 text-xs text-muted-foreground">
                        <div>Status: <span className="text-sm text-slate-900">{diagnostics?.status || "unknown"}</span></div>
                        <div>Verify source: {diagnostics?.verify_token?.effective_source || "none"}</div>
                        <div>Signature source: {diagnostics?.signature?.effective_source || "none"}</div>
                        <div>Signature validation: {diagnostics?.signature?.validation_enabled ? "On" : "Off"}</div>
                    </div>
                )}
            </MetaStatusCard>

            <Card>
                <CardHeader>
                    <CardTitle>Connected Phone Numbers</CardTitle>
                    <CardDescription>Quality rating and throughput are pulled from Meta Graph API.</CardDescription>
                </CardHeader>
                <CardContent>
                    {phoneNumbers.length === 0 ? (
                        <p className="text-sm text-muted-foreground">No phone numbers connected.</p>
                    ) : (
                        <div className="space-y-3">
                            {phoneNumbers.map((phone) => (
                                <div key={phone.id} className="rounded-xl border border-border bg-muted/10 p-3">
                                    <div className="flex flex-wrap items-center justify-between gap-2">
                                        <div>
                                            <div className="text-sm font-semibold">
                                                {phone.display_phone_number || phone.id}
                                            </div>
                                            <div className="text-xs text-muted-foreground">
                                                {phone.verified_name || "Unverified"}
                                            </div>
                                        </div>
                                        <div className="text-xs text-muted-foreground">
                                            Quality: {phone.quality_rating || "n/a"}
                                        </div>
                                    </div>
                                    <div className="mt-2 grid gap-2 text-xs text-muted-foreground sm:grid-cols-2">
                                        <div>Status: {phone.status || "n/a"}</div>
                                        <div>Throughput: {phone.throughput || "n/a"}</div>
                                        <div>Platform: {phone.platform_type || "n/a"}</div>
                                        <div>Verification: {phone.code_verification_status || "n/a"}</div>
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </CardContent>
            </Card>

            <MetaVerificationModal
                isOpen={testModalOpen}
                onClose={() => setTestModalOpen(false)}
                onVerify={handleWebhookTest}
                loading={webhookTestMutation.isPending}
            />
        </div>
    );
}
