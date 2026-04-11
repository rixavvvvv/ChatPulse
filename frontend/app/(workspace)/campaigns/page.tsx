"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { apiRequest } from "@/lib/api";
import { getSession } from "@/lib/session";

type Contact = {
    id: number;
    name: string;
    phone: string;
    tags: string[];
    created_at: string;
};

type Template = {
    id: number;
    name: string;
    body: string;
    variables: string[];
    status: "approved" | "pending" | "rejected";
    created_at: string;
    updated_at: string;
};

type CampaignCreateResponse = {
    id: number;
    template_id: number;
    name: string;
    message_template: string;
    status: "draft" | "queued" | "running" | "completed" | "failed";
    audience_count: number;
    success_count: number;
    failed_count: number;
    queued_job_id: string | null;
    last_error: string | null;
    created_at: string;
    updated_at: string;
};

type CampaignQueueResponse = {
    campaign_id: number;
    status: string;
    job_id: string;
};

type CampaignProgress = {
    campaign_id: number;
    status: "draft" | "queued" | "running" | "completed" | "failed";
    total_count: number;
    processed_count: number;
    sent_count: number;
    failed_count: number;
    skipped_count: number;
    progress_percentage: number;
};

type LaunchMode = "now" | "schedule";

export default function CampaignBuilderPage() {
    const [contacts, setContacts] = useState<Contact[]>([]);
    const [templates, setTemplates] = useState<Template[]>([]);
    const [campaigns, setCampaigns] = useState<CampaignCreateResponse[]>([]);
    const [selectedContactIds, setSelectedContactIds] = useState<number[]>([]);
    const [campaignName, setCampaignName] = useState("April Pipeline Push");
    const [templateId, setTemplateId] = useState<number | null>(null);
    const [scheduleAt, setScheduleAt] = useState("");
    const [newTemplateName, setNewTemplateName] = useState("Lead Followup");
    const [newTemplateBody, setNewTemplateBody] = useState("Hi {{name}}, wanted to check your availability this week.");
    const [activeCampaignId, setActiveCampaignId] = useState<number | null>(null);
    const [activeJobId, setActiveJobId] = useState<string | null>(null);
    const [progress, setProgress] = useState<CampaignProgress | null>(null);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [success, setSuccess] = useState<string | null>(null);

    const selectedTemplate = useMemo(
        () => templates.find((template) => template.id === templateId) ?? null,
        [templates, templateId],
    );
    const canLaunch = selectedTemplate?.status === "approved" && selectedContactIds.length > 0;

    const loadData = useCallback(async () => {
        const session = getSession();
        if (!session) {
            return;
        }

        const [contactsPayload, templatesPayload, campaignsPayload] = await Promise.all([
            apiRequest<Contact[]>("/contacts", {}, session.access_token),
            apiRequest<Template[]>("/templates", {}, session.access_token),
            apiRequest<CampaignCreateResponse[]>("/campaigns", {}, session.access_token),
        ]);

        setContacts(contactsPayload);
        setTemplates(templatesPayload);
        setCampaigns(campaignsPayload);

        if (!templateId && templatesPayload.length > 0) {
            setTemplateId(templatesPayload[0].id);
        }
    }, [templateId]);

    useEffect(() => {
        const run = async () => {
            try {
                await loadData();
            } catch (err) {
                setError(err instanceof Error ? err.message : "Failed to load campaign data");
            }
        };

        void run();
    }, [loadData]);

    useEffect(() => {
        if (!activeCampaignId) {
            return;
        }

        const session = getSession();
        if (!session) {
            return;
        }

        const interval = window.setInterval(async () => {
            try {
                const nextProgress = await apiRequest<CampaignProgress>(
                    `/campaigns/${activeCampaignId}/progress`,
                    {},
                    session.access_token,
                );
                setProgress(nextProgress);
            } catch {
                // Keep last known progress if temporary polling failure occurs.
            }
        }, 2000);

        return () => {
            window.clearInterval(interval);
        };
    }, [activeCampaignId]);

    function toggleContact(contactId: number) {
        setSelectedContactIds((previous) => {
            if (previous.includes(contactId)) {
                return previous.filter((id) => id !== contactId);
            }
            return [...previous, contactId];
        });
    }

    async function handleCreateTemplate(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        const session = getSession();
        if (!session) {
            return;
        }

        setBusy(true);
        setError(null);
        setSuccess(null);
        try {
            const created = await apiRequest<Template>(
                "/templates",
                {
                    method: "POST",
                    body: JSON.stringify({
                        name: newTemplateName,
                        body: newTemplateBody,
                        variables: ["name"],
                    }),
                },
                session.access_token,
            );

            let nextSuccess = "Template created as pending";
            try {
                await apiRequest<Template>(
                    `/templates/${created.id}/status`,
                    {
                        method: "PATCH",
                        body: JSON.stringify({ status: "approved" }),
                    },
                    session.access_token,
                );
                nextSuccess = "Template created and approved";
            } catch {
                nextSuccess = "Template created as pending. Approve it before campaign launch.";
            }

            setSuccess(nextSuccess);
            await loadData();
            setTemplateId(created.id);
        } catch (err) {
            setError(err instanceof Error ? err.message : "Failed to create template");
        } finally {
            setBusy(false);
        }
    }

    async function handleApproveTemplate(nextTemplateId: number) {
        const session = getSession();
        if (!session) {
            return;
        }

        setBusy(true);
        setError(null);
        setSuccess(null);
        try {
            await apiRequest<Template>(
                `/templates/${nextTemplateId}/status`,
                {
                    method: "PATCH",
                    body: JSON.stringify({ status: "approved" }),
                },
                session.access_token,
            );
            setSuccess("Template approved");
            await loadData();
        } catch (err) {
            setError(err instanceof Error ? err.message : "Unable to approve template");
        } finally {
            setBusy(false);
        }
    }

    async function handleLaunchCampaign(mode: LaunchMode) {
        const session = getSession();
        if (!session) {
            return;
        }

        if (!templateId) {
            setError("Select a template before launching.");
            return;
        }

        if (!selectedTemplate || selectedTemplate.status !== "approved") {
            setError("Campaign template must be approved before sending.");
            return;
        }

        if (selectedContactIds.length === 0) {
            setError("Select at least one contact for audience snapshot.");
            return;
        }

        if (mode === "schedule" && !scheduleAt) {
            setError("Select schedule date and time.");
            return;
        }

        setBusy(true);
        setError(null);
        setSuccess(null);

        let createdCampaignId: number | null = null;
        try {
            const created = await apiRequest<CampaignCreateResponse>(
                "/campaigns",
                {
                    method: "POST",
                    body: JSON.stringify({
                        name: campaignName,
                        template_id: templateId,
                    }),
                },
                session.access_token,
            );
            createdCampaignId = created.id;

            await apiRequest(
                `/campaigns/${created.id}/audience`,
                {
                    method: "POST",
                    body: JSON.stringify({ contact_ids: selectedContactIds }),
                },
                session.access_token,
            );

            try {
                const queuePayload = await apiRequest<CampaignQueueResponse>(
                    `/campaigns/${created.id}/queue`,
                    {
                        method: "POST",
                        body: JSON.stringify({
                            schedule_at: mode === "schedule" ? new Date(scheduleAt).toISOString() : null,
                        }),
                    },
                    session.access_token,
                );

                setActiveCampaignId(created.id);
                setActiveJobId(queuePayload.job_id);
                setSuccess(mode === "schedule" ? "Campaign scheduled and queued" : "Campaign queued for immediate send");
            } catch (queueErr) {
                const message = queueErr instanceof Error ? queueErr.message : "Unable to queue campaign";
                setActiveCampaignId(created.id);
                setActiveJobId(null);
                setError(`${message}. Campaign was created and audience saved. Retry from Created Campaigns.`);
            }

            await loadData();
        } catch (err) {
            const message = err instanceof Error ? err.message : "Unable to launch campaign";
            if (createdCampaignId !== null) {
                setActiveCampaignId(createdCampaignId);
                setError(`${message}. Campaign exists and can be retried from Created Campaigns.`);
                await loadData();
            } else {
                setError(message);
            }
        } finally {
            setBusy(false);
        }
    }

    async function handleQueueExistingCampaign(campaignId: number) {
        const session = getSession();
        if (!session) {
            return;
        }

        setBusy(true);
        setError(null);
        setSuccess(null);
        try {
            const queuePayload = await apiRequest<CampaignQueueResponse>(
                `/campaigns/${campaignId}/queue`,
                {
                    method: "POST",
                    body: JSON.stringify({ schedule_at: null }),
                },
                session.access_token,
            );

            setActiveCampaignId(campaignId);
            setActiveJobId(queuePayload.job_id);
            setSuccess("Campaign queued from existing list");
            await loadData();
        } catch (err) {
            setError(err instanceof Error ? err.message : "Unable to queue selected campaign");
        } finally {
            setBusy(false);
        }
    }

    return (
        <div className="space-y-6">
            <section className="rounded-3xl border border-cyan-100 bg-gradient-to-r from-cyan-50 via-sky-50 to-orange-50 p-8 shadow-soft">
                <p className="mb-2 text-xs font-semibold uppercase tracking-[0.22em] text-cyan-700">Flow 2: Campaign Execution</p>
                <h2 className="font-[var(--font-space-grotesk)] text-3xl font-semibold text-slate-900 md:text-4xl">
                    Build, snapshot, queue, and monitor campaigns
                </h2>
                <p className="mt-3 max-w-2xl text-slate-700">
                    Create campaign draft, bind audience snapshot, queue now or schedule for later, and track worker progress live.
                </p>
            </section>

            <div className="grid gap-6 lg:grid-cols-2">
                <Card>
                    <CardHeader>
                        <CardTitle>Create Template</CardTitle>
                        <CardDescription>Quick template authoring with immediate approval for queueing.</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <form className="space-y-3" onSubmit={handleCreateTemplate}>
                            <Input value={newTemplateName} onChange={(event) => setNewTemplateName(event.target.value)} required />
                            <textarea
                                value={newTemplateBody}
                                onChange={(event) => setNewTemplateBody(event.target.value)}
                                className="min-h-24 w-full rounded-xl border border-input bg-background px-3 py-2 text-sm outline-none ring-offset-background focus-visible:ring-2 focus-visible:ring-ring"
                                required
                            />
                            <Button type="submit" disabled={busy}>Create Template</Button>
                        </form>
                    </CardContent>
                </Card>

                <Card>
                    <CardHeader>
                        <CardTitle>Queue Status</CardTitle>
                        <CardDescription>Live campaign execution progress.</CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                        <div className="h-3 overflow-hidden rounded-full bg-slate-200">
                            <div
                                className="h-full rounded-full bg-gradient-to-r from-cyan-500 to-sky-600 transition-all duration-500"
                                style={{ width: `${progress?.progress_percentage ?? 0}%` }}
                            />
                        </div>
                        <p className="text-sm text-slate-700">Progress: {progress?.progress_percentage ?? 0}%</p>
                        <p className="text-sm text-slate-700">Status: {progress?.status ?? "idle"}</p>
                        <p className="text-xs text-slate-500">Campaign ID: {activeCampaignId ?? "-"} | Job ID: {activeJobId ?? "-"}</p>
                        <div className="grid grid-cols-3 gap-2 text-sm">
                            <div className="rounded-lg bg-emerald-50 p-2 text-emerald-800">Sent: {progress?.sent_count ?? 0}</div>
                            <div className="rounded-lg bg-rose-50 p-2 text-rose-800">Failed: {progress?.failed_count ?? 0}</div>
                            <div className="rounded-lg bg-amber-50 p-2 text-amber-800">Skipped: {progress?.skipped_count ?? 0}</div>
                        </div>
                    </CardContent>
                </Card>
            </div>

            <Card>
                <CardHeader>
                    <CardTitle>Campaign Builder</CardTitle>
                    <CardDescription>Select template, audience, then send now or schedule.</CardDescription>
                </CardHeader>
                <CardContent>
                    <form
                        className="space-y-4"
                        onSubmit={(event) => {
                            event.preventDefault();
                        }}
                    >
                        <Input value={campaignName} onChange={(event) => setCampaignName(event.target.value)} required />

                        <div className="grid gap-4 md:grid-cols-2">
                            <div className="space-y-2">
                                <label className="text-sm font-medium text-slate-700">Template</label>
                                <select
                                    value={templateId ?? ""}
                                    onChange={(event) => setTemplateId(Number(event.target.value))}
                                    className="h-10 w-full rounded-xl border border-input bg-background px-3 text-sm"
                                    required
                                >
                                    <option value="" disabled>Select template</option>
                                    {templates.map((template) => (
                                        <option key={template.id} value={template.id}>
                                            {template.name} ({template.status})
                                        </option>
                                    ))}
                                </select>
                                {templates.length === 0 ? <p className="text-xs text-amber-700">No templates available yet.</p> : null}
                                {selectedTemplate && selectedTemplate.status !== "approved" ? (
                                    <p className="text-xs text-amber-700">Selected template is {selectedTemplate.status}. Approve it to launch.</p>
                                ) : null}
                            </div>
                            <div className="space-y-2">
                                <label className="text-sm font-medium text-slate-700">Schedule At</label>
                                <Input
                                    type="datetime-local"
                                    value={scheduleAt}
                                    onChange={(event) => setScheduleAt(event.target.value)}
                                />
                            </div>
                        </div>

                        <div className="rounded-2xl border border-border/70">
                            <Table>
                                <TableHeader>
                                    <TableRow>
                                        <TableHead className="w-14">Pick</TableHead>
                                        <TableHead>Name</TableHead>
                                        <TableHead>Phone</TableHead>
                                    </TableRow>
                                </TableHeader>
                                <TableBody>
                                    {contacts.length === 0 ? (
                                        <TableRow>
                                            <TableCell colSpan={3} className="text-center text-muted-foreground">
                                                No contacts available. Upload CSV in Contacts page first.
                                            </TableCell>
                                        </TableRow>
                                    ) : (
                                        contacts.map((contact) => (
                                            <TableRow key={contact.id}>
                                                <TableCell>
                                                    <input
                                                        type="checkbox"
                                                        checked={selectedContactIds.includes(contact.id)}
                                                        onChange={() => toggleContact(contact.id)}
                                                    />
                                                </TableCell>
                                                <TableCell className="font-medium text-slate-900">{contact.name}</TableCell>
                                                <TableCell className="text-slate-600">{contact.phone}</TableCell>
                                            </TableRow>
                                        ))
                                    )}
                                </TableBody>
                            </Table>
                        </div>

                                <div className="flex flex-wrap gap-3">
                                    <Button
                                        type="button"
                                        disabled={busy || !canLaunch}
                                        onClick={() => {
                                            void handleLaunchCampaign("now");
                                        }}
                                    >
                                        {busy ? "Sending..." : "Send Campaign Now"}
                                    </Button>
                                    <Button
                                        type="button"
                                        variant="outline"
                                        disabled={busy || !canLaunch || !scheduleAt}
                                        onClick={() => {
                                            void handleLaunchCampaign("schedule");
                                        }}
                                    >
                                        {busy ? "Scheduling..." : "Schedule Campaign"}
                                    </Button>
                                </div>
                    </form>
                </CardContent>
            </Card>

            <Card>
                <CardHeader>
                    <CardTitle>Created Campaigns</CardTitle>
                    <CardDescription>All created campaigns. Use this list to retry queueing and monitor any existing campaign.</CardDescription>
                </CardHeader>
                <CardContent>
                    <Table>
                        <TableHeader>
                            <TableRow>
                                <TableHead>Name</TableHead>
                                <TableHead>Status</TableHead>
                                <TableHead>Audience</TableHead>
                                <TableHead>Result</TableHead>
                                <TableHead>Action</TableHead>
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {campaigns.length === 0 ? (
                                <TableRow>
                                    <TableCell colSpan={5} className="text-center text-muted-foreground">
                                        No campaigns created yet.
                                    </TableCell>
                                </TableRow>
                            ) : (
                                campaigns.map((campaign) => (
                                    <TableRow key={campaign.id}>
                                        <TableCell className="font-medium text-slate-900">{campaign.name}</TableCell>
                                        <TableCell className="capitalize text-slate-700">{campaign.status}</TableCell>
                                        <TableCell className="text-slate-700">{campaign.audience_count}</TableCell>
                                        <TableCell className="text-slate-700">S:{campaign.success_count} / F:{campaign.failed_count}</TableCell>
                                        <TableCell className="space-x-2">
                                            <Button
                                                size="sm"
                                                variant="outline"
                                                onClick={() => {
                                                    setActiveCampaignId(campaign.id);
                                                }}
                                            >
                                                View Progress
                                            </Button>
                                            {(campaign.status === "draft" || campaign.status === "failed" || campaign.status === "completed") ? (
                                                <Button
                                                    size="sm"
                                                    disabled={busy || campaign.audience_count === 0}
                                                    onClick={() => {
                                                        void handleQueueExistingCampaign(campaign.id);
                                                    }}
                                                >
                                                    Queue Now
                                                </Button>
                                            ) : null}
                                        </TableCell>
                                    </TableRow>
                                ))
                            )}
                        </TableBody>
                    </Table>
                </CardContent>
            </Card>

                    <Card>
                        <CardHeader>
                            <CardTitle>Template Library</CardTitle>
                            <CardDescription>All templates in this workspace, including pending and rejected.</CardDescription>
                        </CardHeader>
                        <CardContent>
                            <Table>
                                <TableHeader>
                                    <TableRow>
                                        <TableHead>Name</TableHead>
                                        <TableHead>Status</TableHead>
                                        <TableHead>Action</TableHead>
                                    </TableRow>
                                </TableHeader>
                                <TableBody>
                                    {templates.length === 0 ? (
                                        <TableRow>
                                            <TableCell colSpan={3} className="text-center text-muted-foreground">
                                                No templates found.
                                            </TableCell>
                                        </TableRow>
                                    ) : (
                                        templates.map((template) => (
                                            <TableRow key={template.id}>
                                                <TableCell className="font-medium text-slate-900">{template.name}</TableCell>
                                                <TableCell className="capitalize text-slate-700">{template.status}</TableCell>
                                                <TableCell>
                                                    {template.status !== "approved" ? (
                                                        <Button
                                                            size="sm"
                                                            variant="outline"
                                                            disabled={busy}
                                                            onClick={() => {
                                                                void handleApproveTemplate(template.id);
                                                            }}
                                                        >
                                                            Approve
                                                        </Button>
                                                    ) : (
                                                        <span className="text-sm text-emerald-700">Ready</span>
                                                    )}
                                                </TableCell>
                                            </TableRow>
                                        ))
                                    )}
                                </TableBody>
                            </Table>
                        </CardContent>
                    </Card>

            {success ? <p className="text-sm text-emerald-700">{success}</p> : null}
            {error ? <p className="text-sm text-rose-700">{error}</p> : null}
        </div>
    );
}
