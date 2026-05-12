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

type TemplateCategory = "MARKETING" | "UTILITY" | "AUTHENTICATION";
type TemplateHeaderType = "none" | "text" | "image" | "video" | "document";
type TemplateStatus = "draft" | "pending" | "approved" | "rejected";
type TemplateButtonType = "quick_reply" | "url" | "phone_number" | "copy_code";

type TemplateButton = {
    type: TemplateButtonType;
    text: string;
    value: string;
};

type Template = {
    id: number;
    name: string;
    language: string;
    category: TemplateCategory;
    header_type: TemplateHeaderType;
    header_content: string | null;
    body_text: string;
    variables: string[];
    sample_values: string[];
    footer_text: string | null;
    buttons: TemplateButton[];
    status: TemplateStatus;
    meta_template_id: string | null;
    rejection_reason: string | null;
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
type RiskLevel = "Low" | "Medium" | "High";
type RiskIssue = {
    section: "name" | "category" | "header" | "body" | "variables" | "buttons";
    reason: string;
};
type RiskAssessment = {
    score: RiskLevel;
    issues: RiskIssue[];
};

const CATEGORY_OPTIONS: TemplateCategory[] = ["MARKETING", "UTILITY", "AUTHENTICATION"];
const HEADER_OPTIONS: TemplateHeaderType[] = ["none", "text", "image", "video", "document"];
const BUTTON_TYPES: TemplateButtonType[] = ["quick_reply", "url", "phone_number", "copy_code"];
const TEMPLATE_VARIABLE_REGEX = /\{\{\d+\}\}/g;

function extractVariables(bodyText: string): string[] {
    const matches = bodyText.match(TEMPLATE_VARIABLE_REGEX) ?? [];
    return Array.from(new Set(matches));
}

function assessTemplateRisk(input: {
    name: string;
    category: TemplateCategory;
    headerType: TemplateHeaderType;
    headerContent: string;
    body: string;
    variables: string[];
    sampleValues: string[];
    buttons: TemplateButton[];
}): RiskAssessment {
    const issues: RiskIssue[] = [];
    const normalizedBody = input.body.trim();
    const lowerBody = normalizedBody.toLowerCase();

    if (!input.name.trim() || !/^[a-z0-9_]+$/.test(input.name.trim())) {
        issues.push({
            section: "name",
            reason: "Template name should use lowercase letters, numbers, and underscores only.",
        });
    }

    if (normalizedBody.length < 18) {
        issues.push({
            section: "body",
            reason: "Message is too vague or short for Meta review context.",
        });
    }

    if (input.variables.length > 0 && input.sampleValues.some((value) => !value.trim())) {
        issues.push({
            section: "variables",
            reason: "Variable misuse detected: each placeholder should have a meaningful sample value.",
        });
    }

    if (input.category === "MARKETING") {
        const hasOfferSignal = /(offer|discount|sale|promo|deal|save|free|limited)/i.test(lowerBody);
        if (!hasOfferSignal) {
            issues.push({
                section: "category",
                reason: "Marketing category lacks offer language and may be rejected.",
            });
        }
    }

    if (input.headerType !== "none" && !input.headerContent.trim()) {
        issues.push({
            section: "header",
            reason: "Header is enabled but content is missing.",
        });
    }

    for (const button of input.buttons) {
        if (!button.text.trim()) {
            issues.push({
                section: "buttons",
                reason: "Button text cannot be empty.",
            });
            break;
        }
        if (button.type !== "quick_reply" && !button.value.trim()) {
            issues.push({
                section: "buttons",
                reason: `Button '${button.text || button.type}' needs a valid value.`,
            });
            break;
        }
    }

    let score: RiskLevel = "Low";
    if (issues.length >= 3) {
        score = "High";
    } else if (issues.length > 0) {
        score = "Medium";
    }

    return { score, issues };
}

function suggestionForRejection(reason: string | null): string {
    const text = (reason ?? "").toLowerCase();
    if (!text) {
        return "Needs Fix: Add clearer context, complete variable examples, and resubmit.";
    }
    if (text.includes("parameter") || text.includes("invalid")) {
        return "Needs Fix: Validate category/header/buttons fields and ensure placeholders/samples are correctly aligned.";
    }
    if (text.includes("quality") || text.includes("vague")) {
        return "Needs Fix: Make body text specific and explicit about purpose/value.";
    }
    if (text.includes("marketing") || text.includes("promotional")) {
        return "Needs Fix: Add offer details (benefit, CTA, or promotion terms) for marketing templates.";
    }
    return "Needs Fix: Update template wording/fields per rejection reason and submit again.";
}

function normalizeSubmitErrorMessage(message: string): string {
    const lower = message.toLowerCase();
    if (lower.includes("invalid parameter")) {
        return `${message}. Needs Fix: use a lowercase template name with underscores, valid category, and complete header/body/button fields.`;
    }
    return message;
}

export default function CampaignBuilderPage() {
    const [contacts, setContacts] = useState<Contact[]>([]);
    const [templates, setTemplates] = useState<Template[]>([]);
    const [campaigns, setCampaigns] = useState<CampaignCreateResponse[]>([]);
    const [selectedContactIds, setSelectedContactIds] = useState<number[]>([]);
    const [campaignName, setCampaignName] = useState("April Pipeline Push");
    const [templateId, setTemplateId] = useState<number | null>(null);
    const [scheduleAt, setScheduleAt] = useState("");

    const [newTemplateName, setNewTemplateName] = useState("promo_pipeline_followup");
    const [newTemplateLanguage, setNewTemplateLanguage] = useState("en_US");
    const [newTemplateCategory, setNewTemplateCategory] = useState<TemplateCategory>("MARKETING");
    const [newTemplateHeaderType, setNewTemplateHeaderType] = useState<TemplateHeaderType>("none");
    const [newTemplateHeaderContent, setNewTemplateHeaderContent] = useState("");
    const [newTemplateBody, setNewTemplateBody] = useState("Hi {{1}}, we have a new update for you.");
    const [newTemplateSamples, setNewTemplateSamples] = useState<string[]>(["Sample 1"]);
    const [newTemplateFooter, setNewTemplateFooter] = useState("Reply STOP to opt out.");
    const [newTemplateButtons, setNewTemplateButtons] = useState<TemplateButton[]>([]);

    const [activeCampaignId, setActiveCampaignId] = useState<number | null>(null);
    const [activeJobId, setActiveJobId] = useState<string | null>(null);
    const [progress, setProgress] = useState<CampaignProgress | null>(null);
    const [pendingTemplateIds, setPendingTemplateIds] = useState<number[]>([]);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [success, setSuccess] = useState<string | null>(null);

    const selectedTemplate = useMemo(
        () => templates.find((template) => template.id === templateId) ?? null,
        [templates, templateId],
    );
    const canLaunch =
        selectedTemplate?.status === "approved"
        && Boolean(selectedTemplate.meta_template_id)
        && selectedContactIds.length > 0;
    const previewVariables = useMemo(() => extractVariables(newTemplateBody), [newTemplateBody]);
    const approvedTemplates = useMemo(
        () => templates.filter((template) => template.status === "approved" && Boolean(template.meta_template_id)),
        [templates],
    );
    const requestedTemplates = useMemo(
        () => templates.filter(
            (template) => template.status === "draft"
                || template.status === "pending"
                || (template.status === "approved" && !template.meta_template_id),
        ),
        [templates],
    );
    const rejectedTemplates = useMemo(() => templates.filter((template) => template.status === "rejected"), [templates]);
    const draftRiskAssessment = useMemo(
        () =>
            assessTemplateRisk({
                name: newTemplateName,
                category: newTemplateCategory,
                headerType: newTemplateHeaderType,
                headerContent: newTemplateHeaderContent,
                body: newTemplateBody,
                variables: previewVariables,
                sampleValues: newTemplateSamples,
                buttons: newTemplateButtons,
            }),
        [
            newTemplateBody,
            newTemplateButtons,
            newTemplateCategory,
            newTemplateHeaderContent,
            newTemplateHeaderType,
            newTemplateName,
            newTemplateSamples,
            previewVariables,
        ],
    );
    const highlightedSections = useMemo(() => new Set(draftRiskAssessment.issues.map((issue) => issue.section)), [draftRiskAssessment]);

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

        const approvedFromPayload = templatesPayload.filter(
            (template) => template.status === "approved" && Boolean(template.meta_template_id),
        );

        if (!templateId && approvedFromPayload.length > 0) {
            setTemplateId(approvedFromPayload[0].id);
        } else if (!templateId && templatesPayload.length > 0) {
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
        setNewTemplateSamples((previous) => {
            if (previewVariables.length === 0) {
                return [];
            }
            return previewVariables.map((_, index) => previous[index] ?? `Sample ${index + 1}`);
        });
    }, [previewVariables]);

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
                // Keep last known progress when polling fails temporarily.
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

    function insertNextVariable() {
        const variables = extractVariables(newTemplateBody);
        let nextIndex = 1;
        for (const variable of variables) {
            const numberMatch = variable.match(/\d+/);
            if (!numberMatch) {
                continue;
            }
            const tokenNumber = Number(numberMatch[0]);
            if (Number.isFinite(tokenNumber) && tokenNumber >= nextIndex) {
                nextIndex = tokenNumber + 1;
            }
        }

        const spacer = newTemplateBody.trim().length > 0 ? " " : "";
        setNewTemplateBody((prev) => `${prev}${spacer}{{${nextIndex}}}`);
    }

    function addButton() {
        setNewTemplateButtons((previous) => {
            if (previous.length >= 3) {
                return previous;
            }
            return [...previous, { type: "quick_reply", text: "Reply", value: "" }];
        });
    }

    function updateButton(index: number, field: keyof TemplateButton, value: string) {
        setNewTemplateButtons((previous) =>
            previous.map((button, buttonIndex) => {
                if (buttonIndex !== index) {
                    return button;
                }
                if (field === "type") {
                    return { ...button, type: value as TemplateButtonType, value: value === "quick_reply" ? "" : button.value };
                }
                return { ...button, [field]: value };
            }),
        );
    }

    function removeButton(index: number) {
        setNewTemplateButtons((previous) => previous.filter((_, buttonIndex) => buttonIndex !== index));
    }

    function updateSampleValue(index: number, value: string) {
        setNewTemplateSamples((previous) => previous.map((item, itemIndex) => (itemIndex === index ? value : item)));
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
                        language: newTemplateLanguage,
                        category: newTemplateCategory,
                        header_type: newTemplateHeaderType,
                        header_content: newTemplateHeaderType === "none" ? null : newTemplateHeaderContent,
                        body_text: newTemplateBody,
                        variables: extractVariables(newTemplateBody),
                        sample_values: newTemplateSamples,
                        footer_text: newTemplateFooter || null,
                        buttons: newTemplateButtons,
                    }),
                },
                session.access_token,
            );

            setSuccess("Template saved as draft. Submit it to Meta for approval.");
            setTemplateId(created.id);
            await loadData();
        } catch (err) {
            setError(err instanceof Error ? err.message : "Failed to create template");
        } finally {
            setBusy(false);
        }
    }

    async function handleSubmitTemplate(nextTemplateId: number) {
        const session = getSession();
        if (!session) {
            return;
        }

        if (pendingTemplateIds.includes(nextTemplateId)) {
            return;
        }

        setBusy(true);
        setError(null);
        setSuccess(null);
        setPendingTemplateIds((previous) => [...previous, nextTemplateId]);
        setTemplates((previous) =>
            previous.map((template) =>
                template.id === nextTemplateId
                    ? { ...template, status: "pending", rejection_reason: null }
                    : template,
            ),
        );
        try {
            await apiRequest<{ id: number; status: string; meta_template_id: string | null }>(
                `/templates/${nextTemplateId}/submit`,
                {
                    method: "POST",
                },
                session.access_token,
            );
            setSuccess("Template submitted to Meta and moved to pending status.");
            await loadData();
        } catch (err) {
            const message = err instanceof Error ? err.message : "Unable to submit template to Meta";
            setError(normalizeSubmitErrorMessage(message));
            await loadData();
        } finally {
            setPendingTemplateIds((previous) => previous.filter((id) => id !== nextTemplateId));
            setBusy(false);
        }
    }

    async function handleSyncTemplateStatus(nextTemplateId: number) {
        const session = getSession();
        if (!session) {
            return;
        }

        setBusy(true);
        setError(null);
        setSuccess(null);
        try {
            const synced = await apiRequest<Template>(
                `/templates/${nextTemplateId}/status`,
                {
                    method: "GET",
                },
                session.access_token,
            );
            setSuccess(`Template status synced: ${synced.status}`);
            await loadData();
        } catch (err) {
            setError(err instanceof Error ? err.message : "Unable to sync template status");
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
        if (!selectedTemplate.meta_template_id) {
            setError("Selected template is not synced as approved on Meta yet. Submit and sync status first.");
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
                    Build, submit, approve, and launch template campaigns
                </h2>
                <p className="mt-3 max-w-2xl text-slate-700">
                    Templates follow draft to pending to approved/rejected lifecycle through Meta. Only approved templates can be used in campaigns.
                </p>
            </section>

            <div className="grid gap-6 xl:grid-cols-[2fr_1fr]">
                <Card>
                    <CardHeader>
                        <CardTitle>Template Builder</CardTitle>
                        <CardDescription>Create draft template with Meta-compliant fields before submit.</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <form className="space-y-4" onSubmit={handleCreateTemplate}>
                            <div className="grid gap-3 md:grid-cols-3">
                                <Input
                                    value={newTemplateName}
                                    onChange={(event) => setNewTemplateName(event.target.value)}
                                    placeholder="template_name"
                                    className={highlightedSections.has("name") ? "border-rose-300 focus-visible:ring-rose-400" : ""}
                                    required
                                />
                                <Input value={newTemplateLanguage} onChange={(event) => setNewTemplateLanguage(event.target.value)} placeholder="en_US" required />
                                <select
                                    value={newTemplateCategory}
                                    onChange={(event) => setNewTemplateCategory(event.target.value as TemplateCategory)}
                                    className={`h-10 w-full rounded-xl border bg-background px-3 text-sm ${
                                        highlightedSections.has("category") ? "border-rose-300" : "border-input"
                                    }`}
                                >
                                    {CATEGORY_OPTIONS.map((category) => (
                                        <option key={category} value={category}>{category}</option>
                                    ))}
                                </select>
                            </div>

                            <div className="grid gap-3 md:grid-cols-2">
                                <select
                                    value={newTemplateHeaderType}
                                    onChange={(event) => setNewTemplateHeaderType(event.target.value as TemplateHeaderType)}
                                    className={`h-10 w-full rounded-xl border bg-background px-3 text-sm ${
                                        highlightedSections.has("header") ? "border-rose-300" : "border-input"
                                    }`}
                                >
                                    {HEADER_OPTIONS.map((headerType) => (
                                        <option key={headerType} value={headerType}>Header: {headerType}</option>
                                    ))}
                                </select>
                                {newTemplateHeaderType !== "none" ? (
                                    <Input
                                        value={newTemplateHeaderContent}
                                        onChange={(event) => setNewTemplateHeaderContent(event.target.value)}
                                        placeholder={newTemplateHeaderType === "text" ? "Header text" : "Media sample handle or URL"}
                                        className={highlightedSections.has("header") ? "border-rose-300 focus-visible:ring-rose-400" : ""}
                                        required
                                    />
                                ) : (
                                    <Input value="No header" readOnly disabled />
                                )}
                            </div>

                            <div className="space-y-2">
                                <div className="flex items-center justify-between">
                                    <label className="text-sm font-medium text-slate-700">Body</label>
                                    <Button type="button" size="sm" variant="outline" onClick={insertNextVariable}>
                                        Insert Variable
                                    </Button>
                                </div>
                                <textarea
                                    value={newTemplateBody}
                                    onChange={(event) => setNewTemplateBody(event.target.value)}
                                    className={`min-h-28 w-full rounded-xl border bg-background px-3 py-2 text-sm outline-none ring-offset-background focus-visible:ring-2 ${
                                        highlightedSections.has("body") ? "border-rose-300 focus-visible:ring-rose-400" : "border-input focus-visible:ring-ring"
                                    }`}
                                    required
                                />
                                <p className="text-xs text-slate-600">Detected variables: {previewVariables.join(", ") || "none"}</p>
                            </div>

                            {previewVariables.length > 0 ? (
                                <div className="space-y-2 rounded-2xl border border-border/70 p-3">
                                    <p className="text-sm font-medium text-slate-700">Sample Values (required for Meta review)</p>
                                    {previewVariables.map((variable, index) => (
                                        <Input
                                            key={variable}
                                            value={newTemplateSamples[index] ?? ""}
                                            onChange={(event) => updateSampleValue(index, event.target.value)}
                                            placeholder={`Example for ${variable}`}
                                            className={highlightedSections.has("variables") ? "border-rose-300 focus-visible:ring-rose-400" : ""}
                                            required
                                        />
                                    ))}
                                </div>
                            ) : null}

                            <Input
                                value={newTemplateFooter}
                                onChange={(event) => setNewTemplateFooter(event.target.value)}
                                placeholder="Footer (optional)"
                            />

                            <div
                                className={`space-y-2 rounded-2xl border p-3 ${
                                    highlightedSections.has("buttons") ? "border-rose-300" : "border-border/70"
                                }`}
                            >
                                <div className="flex items-center justify-between">
                                    <p className="text-sm font-medium text-slate-700">Buttons (max 3)</p>
                                    <Button type="button" size="sm" variant="outline" onClick={addButton} disabled={newTemplateButtons.length >= 3}>
                                        Add Button
                                    </Button>
                                </div>

                                {newTemplateButtons.length === 0 ? <p className="text-xs text-slate-500">No buttons configured.</p> : null}

                                {newTemplateButtons.map((button, index) => (
                                    <div key={`${button.type}-${index}`} className="grid gap-2 md:grid-cols-[140px_1fr_1fr_auto]">
                                        <select
                                            value={button.type}
                                            onChange={(event) => updateButton(index, "type", event.target.value)}
                                            className="h-10 rounded-xl border border-input bg-background px-3 text-sm"
                                        >
                                            {BUTTON_TYPES.map((type) => (
                                                <option key={type} value={type}>{type}</option>
                                            ))}
                                        </select>
                                        <Input
                                            value={button.text}
                                            onChange={(event) => updateButton(index, "text", event.target.value)}
                                            placeholder="Button text"
                                            required
                                        />
                                        <Input
                                            value={button.value}
                                            onChange={(event) => updateButton(index, "value", event.target.value)}
                                            placeholder="Value (URL/phone/code)"
                                            disabled={button.type === "quick_reply"}
                                        />
                                        <Button type="button" size="sm" variant="outline" onClick={() => removeButton(index)}>
                                            Remove
                                        </Button>
                                    </div>
                                ))}
                            </div>

                            <Button type="submit" disabled={busy}>Save Draft Template</Button>

                            <div className="rounded-2xl border border-border/70 bg-slate-50 p-3 text-sm">
                                <p className="font-semibold text-slate-900">Pre-Submission Risk Engine</p>
                                <p className="mt-1 text-slate-700">Risk Score: {draftRiskAssessment.score}</p>
                                {draftRiskAssessment.issues.length === 0 ? (
                                    <p className="mt-1 text-emerald-700">No obvious rejection signals detected.</p>
                                ) : (
                                    <ul className="mt-2 list-disc space-y-1 pl-5 text-rose-700">
                                        {draftRiskAssessment.issues.map((issue, idx) => (
                                            <li key={`${issue.section}-${idx}`}>{issue.reason}</li>
                                        ))}
                                    </ul>
                                )}
                            </div>
                        </form>
                    </CardContent>
                </Card>

                <Card>
                    <CardHeader>
                        <CardTitle>Live Preview</CardTitle>
                        <CardDescription>Operator preview of rendered template sections.</CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-3">
                        <div className="rounded-2xl border border-border/70 bg-slate-50 p-3 text-sm">
                            <p className="text-xs uppercase tracking-wide text-slate-500">Header</p>
                            <p className="mt-1 text-slate-800">
                                {newTemplateHeaderType === "none" ? "(none)" : `${newTemplateHeaderType}: ${newTemplateHeaderContent || "(empty)"}`}
                            </p>
                        </div>
                        <div className="rounded-2xl border border-border/70 bg-slate-50 p-3 text-sm">
                            <p className="text-xs uppercase tracking-wide text-slate-500">Body</p>
                            <p className="mt-1 whitespace-pre-wrap text-slate-900">{newTemplateBody}</p>
                        </div>
                        <div className="rounded-2xl border border-border/70 bg-slate-50 p-3 text-sm">
                            <p className="text-xs uppercase tracking-wide text-slate-500">Variable Samples</p>
                            {previewVariables.length === 0 ? <p className="mt-1 text-slate-600">(none)</p> : null}
                            {previewVariables.map((variable, index) => (
                                <p key={variable} className="mt-1 text-slate-700">
                                    {variable}: {newTemplateSamples[index] || "(empty)"}
                                </p>
                            ))}
                        </div>
                        <div className="rounded-2xl border border-border/70 bg-slate-50 p-3 text-sm">
                            <p className="text-xs uppercase tracking-wide text-slate-500">Footer</p>
                            <p className="mt-1 text-slate-700">{newTemplateFooter || "(none)"}</p>
                        </div>
                        <div className="rounded-2xl border border-border/70 bg-slate-50 p-3 text-sm">
                            <p className="text-xs uppercase tracking-wide text-slate-500">Buttons</p>
                            {newTemplateButtons.length === 0 ? <p className="mt-1 text-slate-600">(none)</p> : null}
                            {newTemplateButtons.map((button, index) => (
                                <p key={`${button.type}-${index}`} className="mt-1 text-slate-700">
                                    {button.type}: {button.text}{button.value ? ` (${button.value})` : ""}
                                </p>
                            ))}
                        </div>
                    </CardContent>
                </Card>
            </div>

            <div className="grid gap-6 lg:grid-cols-2">
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
                        <p className="text-xs text-slate-500">
                            Counts below reflect provider acceptance. Delivery/read updates arrive later via Meta webhooks.
                        </p>
                        <div className="grid grid-cols-3 gap-2 text-sm">
                            <div className="rounded-lg bg-emerald-50 p-2 text-emerald-800">Accepted: {progress?.sent_count ?? 0}</div>
                            <div className="rounded-lg bg-rose-50 p-2 text-rose-800">Failed: {progress?.failed_count ?? 0}</div>
                            <div className="rounded-lg bg-amber-50 p-2 text-amber-800">Skipped: {progress?.skipped_count ?? 0}</div>
                        </div>
                    </CardContent>
                </Card>

                <Card>
                    <CardHeader>
                        <CardTitle>Campaign Builder</CardTitle>
                        <CardDescription>Select approved template, bind audience, then send now or schedule.</CardDescription>
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
                                                {template.name} ({template.status}{template.meta_template_id ? ", meta" : ", local"})
                                            </option>
                                        ))}
                                    </select>
                                    {templates.length === 0 ? <p className="text-xs text-amber-700">No templates available yet.</p> : null}
                                    {selectedTemplate && selectedTemplate.status !== "approved" ? (
                                        <p className="text-xs text-amber-700">Selected template is {selectedTemplate.status}. It must be approved before launch.</p>
                                    ) : null}
                                    {selectedTemplate && selectedTemplate.status === "approved" && !selectedTemplate.meta_template_id ? (
                                        <p className="text-xs text-amber-700">Template is locally approved but not synced with Meta yet.</p>
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
            </div>

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
                                        <TableCell className="text-slate-700">A:{campaign.success_count} / F:{campaign.failed_count}</TableCell>
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

            <div className="grid gap-6 xl:grid-cols-2">
                <Card>
                    <CardHeader>
                        <CardTitle>Requested Templates</CardTitle>
                        <CardDescription>Draft + pending templates waiting for Meta submission or approval.</CardDescription>
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
                                {requestedTemplates.length === 0 ? (
                                    <TableRow>
                                        <TableCell colSpan={3} className="text-center text-muted-foreground">
                                            No requested templates.
                                        </TableCell>
                                    </TableRow>
                                ) : (
                                    requestedTemplates.map((template) => (
                                        <TableRow key={template.id}>
                                            <TableCell className="font-medium text-slate-900">{template.name}</TableCell>
                                            <TableCell className="capitalize text-slate-700">{template.status}</TableCell>
                                            <TableCell className="space-x-2">
                                                {template.status === "draft" || pendingTemplateIds.includes(template.id) ? (
                                                    <Button
                                                        size="sm"
                                                        variant="outline"
                                                        disabled={busy || pendingTemplateIds.includes(template.id)}
                                                        onClick={() => {
                                                            void handleSubmitTemplate(template.id);
                                                        }}
                                                    >
                                                        {pendingTemplateIds.includes(template.id) ? "Waiting for approval" : "Submit to Meta"}
                                                    </Button>
                                                ) : null}
                                                {template.status === "pending" || (template.status === "approved" && !template.meta_template_id) ? (
                                                    <Button
                                                        size="sm"
                                                        variant="outline"
                                                        disabled={busy}
                                                        onClick={() => {
                                                            void handleSyncTemplateStatus(template.id);
                                                        }}
                                                    >
                                                        Sync Status
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
                        <CardTitle>Approved Meta Templates</CardTitle>
                        <CardDescription>Templates ready for campaign launch.</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <Table>
                            <TableHeader>
                                <TableRow>
                                    <TableHead>Name</TableHead>
                                    <TableHead>Category</TableHead>
                                    <TableHead>Meta ID</TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {approvedTemplates.length === 0 ? (
                                    <TableRow>
                                        <TableCell colSpan={3} className="text-center text-muted-foreground">
                                            No approved templates yet.
                                        </TableCell>
                                    </TableRow>
                                ) : (
                                    approvedTemplates.map((template) => (
                                        <TableRow key={template.id}>
                                            <TableCell className="font-medium text-slate-900">{template.name}</TableCell>
                                            <TableCell className="text-slate-700">{template.category}</TableCell>
                                            <TableCell className="max-w-[240px] truncate text-xs text-slate-600">{template.meta_template_id ?? "-"}</TableCell>
                                        </TableRow>
                                    ))
                                )}
                            </TableBody>
                        </Table>
                    </CardContent>
                </Card>
            </div>

            <Card>
                <CardHeader>
                    <CardTitle>Rejected Templates</CardTitle>
                    <CardDescription>Fix and resubmit templates rejected by Meta.</CardDescription>
                </CardHeader>
                <CardContent>
                    <Table>
                        <TableHeader>
                            <TableRow>
                                <TableHead>Name</TableHead>
                                <TableHead>Reason</TableHead>
                                <TableHead>Action</TableHead>
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {rejectedTemplates.length === 0 ? (
                                <TableRow>
                                    <TableCell colSpan={3} className="text-center text-muted-foreground">
                                        No rejected templates.
                                    </TableCell>
                                </TableRow>
                            ) : (
                                rejectedTemplates.map((template) => (
                                    <TableRow key={template.id}>
                                        <TableCell className="font-medium text-slate-900">{template.name}</TableCell>
                                        <TableCell className="space-y-1 text-slate-700">
                                            <p>{template.rejection_reason ?? "No rejection reason returned"}</p>
                                            <p className="text-xs text-amber-700">{suggestionForRejection(template.rejection_reason)}</p>
                                        </TableCell>
                                        <TableCell>
                                            <Button
                                                size="sm"
                                                variant="outline"
                                                disabled={busy}
                                                onClick={() => {
                                                    void handleSubmitTemplate(template.id);
                                                }}
                                            >
                                                Resubmit
                                            </Button>
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
