"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { Loader2, ShoppingBag } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { apiRequest, getApiUrl } from "@/lib/api";
import { getSession } from "@/lib/session";

type EcommerceStore = {
    id: number;
    workspace_id: number;
    store_identifier: string;
    access_token_configured: boolean;
};

type EventMapping = {
    id: number;
    workspace_id: number;
    event_type: string;
    template_id: number;
};

type TemplateListItem = {
    id: number;
    name: string;
    language: string;
    body_text: string;
    status: string;
    meta_template_id: string | null;
};

const ORDER_EVENT = "order_created";

export default function ShopifyIntegrationPage() {
    const [stores, setStores] = useState<EcommerceStore[]>([]);
    const [mappings, setMappings] = useState<EventMapping[]>([]);
    const [templates, setTemplates] = useState<TemplateListItem[]>([]);
    const [loading, setLoading] = useState(true);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [success, setSuccess] = useState<string | null>(null);

    const [storeIdentifier, setStoreIdentifier] = useState("");
    const [webhookSecret, setWebhookSecret] = useState("");
    const [accessToken, setAccessToken] = useState("");
    const [mappingTemplateId, setMappingTemplateId] = useState<number | "">("");

    const webhookUrlPlain = useMemo(() => getApiUrl("/webhook/order-created"), []);

    const loadAll = useCallback(async () => {
        const session = getSession();
        if (!session) {
            setLoading(false);
            setError("Login required");
            return;
        }
        setError(null);
        try {
            const [storeRows, mapRows, templateRows] = await Promise.all([
                apiRequest<EcommerceStore[]>("/ecommerce/stores", {}, session.access_token),
                apiRequest<EventMapping[]>("/ecommerce/event-mappings", {}, session.access_token),
                apiRequest<TemplateListItem[]>("/templates", {}, session.access_token),
            ]);
            setStores(storeRows);
            setMappings(mapRows);
            setTemplates(templateRows);
            const existing = mapRows.find((m) => m.event_type === ORDER_EVENT);
            if (existing) {
                setMappingTemplateId(existing.template_id);
            }
        } catch (err) {
            setError(err instanceof Error ? err.message : "Failed to load integration settings");
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        void loadAll();
    }, [loadAll]);

    const approvedTemplates = useMemo(
        () => templates.filter((t) => t.status === "approved" && t.meta_template_id),
        [templates],
    );

    async function handleAddStore(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        const session = getSession();
        if (!session) {
            setError("Login required");
            return;
        }
        setBusy(true);
        setError(null);
        setSuccess(null);
        try {
            const body: Record<string, string | undefined> = {
                store_identifier: storeIdentifier.trim(),
                webhook_secret: webhookSecret,
            };
            if (accessToken.trim()) {
                body.access_token = accessToken.trim();
            }
            await apiRequest<EcommerceStore>(
                "/ecommerce/stores",
                {
                    method: "POST",
                    body: JSON.stringify(body),
                },
                session.access_token,
            );
            setStoreIdentifier("");
            setWebhookSecret("");
            setAccessToken("");
            setSuccess("Store connection saved. Use the webhook URL below in Shopify.");
            await loadAll();
        } catch (err) {
            setError(err instanceof Error ? err.message : "Could not save store");
        } finally {
            setBusy(false);
        }
    }

    async function handleSaveMapping(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        const session = getSession();
        if (!session) {
            setError("Login required");
            return;
        }
        if (mappingTemplateId === "") {
            setError("Choose an approved template");
            return;
        }
        setBusy(true);
        setError(null);
        setSuccess(null);
        try {
            await apiRequest<EventMapping>(
                "/ecommerce/event-mappings",
                {
                    method: "PUT",
                    body: JSON.stringify({
                        event_type: ORDER_EVENT,
                        template_id: mappingTemplateId,
                    }),
                },
                session.access_token,
            );
            setSuccess("Order template mapping saved.");
            await loadAll();
        } catch (err) {
            setError(err instanceof Error ? err.message : "Could not save mapping");
        } finally {
            setBusy(false);
        }
    }

    return (
        <div className="space-y-6">
            <section className="rounded-3xl border border-border/80 bg-white/85 p-6 shadow-soft">
                <p className="text-xs font-semibold uppercase tracking-[0.22em] text-sky-700">Integrations</p>
                <h2 className="mt-2 flex items-center gap-2 font-[var(--font-space-grotesk)] text-3xl font-semibold text-slate-900">
                    <ShoppingBag className="h-8 w-8 text-sky-700" />
                    Shopify
                </h2>
                <p className="mt-2 text-sm text-muted-foreground">
                    Connect your store webhook to send WhatsApp order notifications using an approved Meta template (utility
                    category recommended).
                </p>
            </section>

            <Card>
                <CardHeader>
                    <CardTitle>Webhook URL</CardTitle>
                    <CardDescription>
                        In Shopify: Settings → Notifications → Webhooks (or Apps → your app). Use the same signing secret you
                        save under &quot;Webhook secret&quot; below. Shopify sends{" "}
                        <code className="rounded bg-muted px-1 text-xs">X-Shopify-Hmac-Sha256</code> — the API verifies it
                        automatically.
                    </CardDescription>
                </CardHeader>
                <CardContent className="space-y-3 text-sm">
                    <div>
                        <p className="mb-1 font-medium text-slate-800">Option A — domain in URL</p>
                        <code className="block break-all rounded-xl border border-border bg-muted/40 px-3 py-2 text-xs">
                            {webhookUrlPlain}/your-store.myshopify.com
                        </code>
                    </div>
                    <div>
                        <p className="mb-1 font-medium text-slate-800">Option B — fixed URL (Shopify sends shop domain header)</p>
                        <code className="block break-all rounded-xl border border-border bg-muted/40 px-3 py-2 text-xs">
                            {webhookUrlPlain}
                        </code>
                        <p className="mt-1 text-xs text-muted-foreground">
                            Your <strong>store identifier</strong> here must match{" "}
                            <code className="rounded bg-muted px-1">X-Shopify-Shop-Domain</code> (e.g.{" "}
                            <code className="rounded bg-muted px-1">cool.myshopify.com</code>).
                        </p>
                    </div>
                </CardContent>
            </Card>

            <Card>
                <CardHeader>
                    <CardTitle>Template variables</CardTitle>
                    <CardDescription>
                        Meta templates use numbered placeholders. Map your approved template body to:{" "}
                        <code className="rounded bg-muted px-1">{"{{1}}"}</code> customer name,{" "}
                        <code className="rounded bg-muted px-1">{"{{2}}"}</code> order id,{" "}
                        <code className="rounded bg-muted px-1">{"{{3}}"}</code> total amount,{" "}
                        <code className="rounded bg-muted px-1">{"{{4}}"}</code> phone (optional).
                    </CardDescription>
                </CardHeader>
            </Card>

            <div className="grid gap-6 lg:grid-cols-2">
                <Card>
                    <CardHeader>
                        <CardTitle>Store connection</CardTitle>
                        <CardDescription>
                            {loading ? "Loading…" : `${stores.length} store(s) connected`}
                        </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                        {stores.length > 0 ? (
                            <ul className="space-y-2 rounded-xl border border-border bg-muted/20 p-3 text-sm">
                                {stores.map((s) => (
                                    <li key={s.id} className="flex justify-between gap-2">
                                        <span className="font-medium text-slate-900">{s.store_identifier}</span>
                                        <span className="text-muted-foreground">
                                            {s.access_token_configured ? "Token saved" : "No admin token"}
                                        </span>
                                    </li>
                                ))}
                            </ul>
                        ) : null}

                        <form className="space-y-3" onSubmit={handleAddStore}>
                            <div>
                                <label className="text-sm font-medium text-slate-800" htmlFor="shopify-store-id">
                                    Store identifier
                                </label>
                                <Input
                                    id="shopify-store-id"
                                    className="mt-1"
                                    placeholder="your-store.myshopify.com"
                                    value={storeIdentifier}
                                    onChange={(e) => setStoreIdentifier(e.target.value)}
                                    required
                                />
                            </div>
                            <div>
                                <label className="text-sm font-medium text-slate-800" htmlFor="shopify-secret">
                                    Webhook secret (HMAC)
                                </label>
                                <Input
                                    id="shopify-secret"
                                    className="mt-1"
                                    type="password"
                                    autoComplete="new-password"
                                    placeholder="Same secret configured in Shopify for this webhook"
                                    value={webhookSecret}
                                    onChange={(e) => setWebhookSecret(e.target.value)}
                                    required
                                    minLength={8}
                                />
                            </div>
                            <div>
                                <label className="text-sm font-medium text-slate-800" htmlFor="shopify-admin-token">
                                    Admin API access token (optional)
                                </label>
                                <Input
                                    id="shopify-admin-token"
                                    className="mt-1"
                                    type="password"
                                    autoComplete="new-password"
                                    placeholder="For future features"
                                    value={accessToken}
                                    onChange={(e) => setAccessToken(e.target.value)}
                                />
                            </div>
                            <Button type="submit" className="w-full" disabled={busy}>
                                {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                                Add store
                            </Button>
                        </form>
                    </CardContent>
                </Card>

                <Card>
                    <CardHeader>
                        <CardTitle>Order → WhatsApp template</CardTitle>
                        <CardDescription>
                            Event <code className="rounded bg-muted px-1">{ORDER_EVENT}</code>. Choose an approved template
                            synced with Meta.
                        </CardDescription>
                    </CardHeader>
                    <CardContent>
                        {mappings.filter((m) => m.event_type === ORDER_EVENT).length > 0 ? (
                            <p className="mb-3 text-sm text-emerald-800">
                                Mapping active (template id{" "}
                                {mappings.find((m) => m.event_type === ORDER_EVENT)?.template_id}).
                            </p>
                        ) : (
                            <p className="mb-3 text-sm text-amber-800">No mapping yet — select a template and save.</p>
                        )}
                        <form className="space-y-3" onSubmit={handleSaveMapping}>
                            <div>
                                <label className="text-sm font-medium text-slate-800" htmlFor="shopify-template">
                                    Approved template
                                </label>
                                <select
                                    id="shopify-template"
                                    className="mt-1 w-full rounded-xl border border-input bg-background px-3 py-2 text-sm outline-none ring-offset-background focus-visible:ring-2 focus-visible:ring-ring"
                                    value={mappingTemplateId === "" ? "" : String(mappingTemplateId)}
                                    onChange={(e) => {
                                        const v = e.target.value;
                                        setMappingTemplateId(v === "" ? "" : Number(v));
                                    }}
                                >
                                    <option value="">— Select —</option>
                                    {approvedTemplates.map((t) => (
                                        <option key={t.id} value={t.id}>
                                            {t.name} ({t.language})
                                        </option>
                                    ))}
                                </select>
                                {approvedTemplates.length === 0 && !loading ? (
                                    <p className="mt-1 text-xs text-muted-foreground">
                                        No approved templates. Create one under Campaign Builder and submit to Meta first.
                                    </p>
                                ) : null}
                            </div>
                            <Button type="submit" className="w-full" variant="secondary" disabled={busy || loading}>
                                Save mapping
                            </Button>
                        </form>
                    </CardContent>
                </Card>
            </div>

            {error ? <p className="text-sm text-rose-700">{error}</p> : null}
            {success ? <p className="text-sm text-emerald-700">{success}</p> : null}
        </div>
    );
}
