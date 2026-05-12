"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Loader2, SendHorizonal } from "lucide-react";

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

type TemplateStatus = "draft" | "pending" | "approved" | "rejected";

type WaTemplate = {
    id: number;
    name: string;
    language: string;
    body_text: string;
    status: TemplateStatus;
    meta_template_id: string | null;
};

type BulkSendResult = {
    success_count: number;
    failed_count: number;
    results: {
        contact_id: number;
        phone: string | null;
        status: string;
        provider: string | null;
        message_id: string | null;
        error: string | null;
    }[];
};

const PAGE_SIZE = 5;

function previewMessage(template: string, name: string) {
    return template.replace(/\{\{\s*name\s*\}\}/gi, name);
}

function explainDeliveryError(message: string | null): string | null {
    if (!message) {
        return null;
    }
    const lower = message.toLowerCase();
    if (lower.includes("recipient phone number not in allowed list")) {
        return "Meta still rejected the `to` number. Use full international digits only in contacts (e.g. 919682852240), set WHATSAPP_DEFAULT_CALLING_CODE=91 on the API if you store 10-digit locals, and ensure the allowlist uses the same digits (no +). Also confirm this app’s Phone Number ID / token matches the Meta project where you added the recipient.";
    }
    if (lower.includes("re-engagement") || lower.includes("24 hour") || lower.includes("24-hour")) {
        return "WhatsApp blocks free-form business messages outside the customer care window. Use an approved template (select one above) for cold outreach.";
    }
    if (lower.includes("template") && (lower.includes("required") || lower.includes("invalid"))) {
        return "Check that the template is approved on Meta, the template name matches exactly, and variable counts match your template body.";
    }
    return null;
}

export default function BulkMessagingPage() {
    const [contacts, setContacts] = useState<Contact[]>([]);
    const [templates, setTemplates] = useState<WaTemplate[]>([]);
    const [loadingTemplates, setLoadingTemplates] = useState(true);
    const [selectedTemplateId, setSelectedTemplateId] = useState<number | null>(null);
    const [messageTemplate, setMessageTemplate] = useState(
        "Hi {{name}}, just checking in with your latest update.",
    );
    const [search, setSearch] = useState("");
    const [currentPage, setCurrentPage] = useState(1);
    const [selectedContactIds, setSelectedContactIds] = useState<number[]>([]);
    const [isSending, setIsSending] = useState(false);
    const [loadingContacts, setLoadingContacts] = useState(true);
    const [result, setResult] = useState<BulkSendResult | null>(null);
    const [errorMessage, setErrorMessage] = useState<string | null>(null);

    const loadContacts = useCallback(async () => {
        const session = getSession();
        if (!session) {
            setLoadingContacts(false);
            setErrorMessage("Login required to load contacts");
            return;
        }

        try {
            const payload = await apiRequest<Contact[]>("/contacts", {}, session.access_token);
            setContacts(payload);
        } catch (err) {
            setErrorMessage(err instanceof Error ? err.message : "Unable to load contacts");
        } finally {
            setLoadingContacts(false);
        }
    }, []);

    const loadTemplates = useCallback(async () => {
        const session = getSession();
        if (!session) {
            setLoadingTemplates(false);
            return;
        }
        try {
            const payload = await apiRequest<WaTemplate[]>("/templates", {}, session.access_token);
            setTemplates(payload);
        } catch {
            setTemplates([]);
        } finally {
            setLoadingTemplates(false);
        }
    }, []);

    useEffect(() => {
        void loadContacts();
    }, [loadContacts]);

    useEffect(() => {
        void loadTemplates();
    }, [loadTemplates]);

    const approvedTemplates = useMemo(() => {
        return templates.filter((t) => t.status === "approved" && t.meta_template_id);
    }, [templates]);

    const selectedTemplate = useMemo(() => {
        return templates.find((t) => t.id === selectedTemplateId) ?? null;
    }, [templates, selectedTemplateId]);

    const filteredContacts = useMemo(() => {
        const query = search.trim().toLowerCase();
        if (!query) {
            return contacts;
        }
        return contacts.filter((contact) => {
            return (
                contact.name.toLowerCase().includes(query) ||
                contact.phone.toLowerCase().includes(query)
            );
        });
    }, [contacts, search]);

    const totalPages = Math.max(1, Math.ceil(filteredContacts.length / PAGE_SIZE));
    const safePage = Math.min(currentPage, totalPages);

    const visibleContacts = useMemo(() => {
        const start = (safePage - 1) * PAGE_SIZE;
        return filteredContacts.slice(start, start + PAGE_SIZE);
    }, [filteredContacts, safePage]);

    const selectedOnPageCount = visibleContacts.filter((contact) => selectedContactIds.includes(contact.id)).length;
    const selectedPreviewContact = contacts.find((contact) => contact.id === selectedContactIds[0]) ?? filteredContacts[0] ?? null;
    const contactsById = useMemo(() => {
        return new Map(contacts.map((contact) => [contact.id, contact]));
    }, [contacts]);

    const previewText = selectedTemplate
        ? selectedTemplate.body_text
              .replace(/\{\{\s*1\s*\}\}/g, selectedPreviewContact?.name ?? "Contact")
              .replace(/\{\{\s*2\s*\}\}/g, selectedPreviewContact?.phone ?? "+10000000000")
        : previewMessage(messageTemplate, selectedPreviewContact?.name ?? "Contact");

    function toggleContact(contactId: number) {
        setSelectedContactIds((prev) => {
            if (prev.includes(contactId)) {
                return prev.filter((id) => id !== contactId);
            }
            return [...prev, contactId];
        });
    }

    function toggleSelectCurrentPage() {
        const pageIds = visibleContacts.map((contact) => contact.id);
        const allSelected = pageIds.every((id) => selectedContactIds.includes(id));

        setSelectedContactIds((prev) => {
            if (allSelected) {
                return prev.filter((id) => !pageIds.includes(id));
            }
            const merged = new Set([...prev, ...pageIds]);
            return Array.from(merged);
        });
    }

    async function handleSend() {
        if (selectedContactIds.length === 0) {
            setErrorMessage("Select at least one contact before sending.");
            setResult(null);
            return;
        }

        const session = getSession();
        if (!session) {
            setErrorMessage("Login required to send messages");
            setResult(null);
            return;
        }

        setIsSending(true);
        setErrorMessage(null);

        try {
            const body: Record<string, unknown> = {
                message_template: selectedTemplate ? "" : messageTemplate,
                contact_ids: selectedContactIds,
            };
            if (selectedTemplateId != null) {
                body.template_id = selectedTemplateId;
            }
            const data = await apiRequest<BulkSendResult>(
                "/bulk-send",
                {
                    method: "POST",
                    body: JSON.stringify(body),
                },
                session.access_token,
            );

            setResult({
                success_count: data.success_count ?? 0,
                failed_count: data.failed_count ?? 0,
                results: Array.isArray(data.results) ? data.results : [],
            });
        } catch (err) {
            setResult(null);
            setErrorMessage(err instanceof Error ? err.message : "Unable to send bulk message");
        } finally {
            setIsSending(false);
        }
    }

    return (
        <div className="space-y-6">
            <section className="rounded-3xl border border-border/80 bg-white/85 p-6 shadow-soft">
                <p className="text-xs font-semibold uppercase tracking-[0.22em] text-sky-700">Campaign Composer</p>
                <h2 className="mt-2 font-[var(--font-space-grotesk)] text-3xl font-semibold text-slate-900">
                    Bulk Messaging
                </h2>
                <p className="mt-2 text-sm text-muted-foreground">
                    For Meta WhatsApp Cloud, choose an approved message template for business-initiated sends. Free-form text
                    only works inside the 24-hour customer care window.
                </p>
            </section>

            <div className="grid gap-6 xl:grid-cols-[1.2fr_1fr]">
                <Card>
                    <CardHeader>
                        <CardTitle>Message</CardTitle>
                        <CardDescription>
                            WhatsApp template (Meta): {"{{1}}"} is filled with the contact name, {"{{2}}"} with phone. Or
                            use free-form text only if the user messaged you within 24 hours.
                        </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                        <div className="space-y-2">
                            <label htmlFor="wa-template-select" className="text-sm font-medium text-slate-800">
                                Approved WhatsApp template
                            </label>
                            <select
                                id="wa-template-select"
                                value={selectedTemplateId ?? ""}
                                onChange={(e) => {
                                    const v = e.target.value;
                                    setSelectedTemplateId(v === "" ? null : Number(v));
                                }}
                                disabled={loadingTemplates}
                                className="w-full rounded-2xl border border-input bg-background px-4 py-2.5 text-sm outline-none ring-offset-background focus-visible:ring-2 focus-visible:ring-ring"
                            >
                                <option value="">
                                    {loadingTemplates ? "Loading templates…" : "— Free-form only (24h session) —"}
                                </option>
                                {approvedTemplates.map((t) => (
                                    <option key={t.id} value={t.id}>
                                        {t.name} ({t.language})
                                    </option>
                                ))}
                            </select>
                            {approvedTemplates.length === 0 && !loadingTemplates ? (
                                <p className="text-xs text-amber-800">
                                    No approved templates found. Create and submit one on the Campaigns page, then refresh.
                                </p>
                            ) : null}
                        </div>

                        <textarea
                            value={messageTemplate}
                            onChange={(event) => setMessageTemplate(event.target.value)}
                            disabled={Boolean(selectedTemplate)}
                            className="min-h-36 w-full rounded-2xl border border-input bg-background px-4 py-3 text-sm outline-none ring-offset-background focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-60"
                            placeholder={
                                selectedTemplate
                                    ? "Using Meta template body (see preview below)"
                                    : "Type your campaign message (use {{name}} for contact name)"
                            }
                        />

                        <div className="rounded-2xl border border-sky-100 bg-sky-50/80 p-4">
                            <p className="mb-2 text-xs font-semibold uppercase tracking-[0.16em] text-sky-700">Preview</p>
                            <p className="text-sm text-slate-700">{previewText}</p>
                            <p className="mt-2 text-xs text-slate-500">
                                Preview contact: {selectedPreviewContact?.name ?? "No contact selected"}
                            </p>
                        </div>
                    </CardContent>
                </Card>

                <Card>
                    <CardHeader>
                        <CardTitle>Send</CardTitle>
                        <CardDescription>{selectedContactIds.length} contacts selected</CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                        <Button
                            onClick={handleSend}
                            className="w-full gap-2"
                            disabled={
                                isSending || (!selectedTemplate && !messageTemplate.trim())
                            }
                        >
                            {isSending ? <Loader2 className="h-4 w-4 animate-spin" /> : <SendHorizonal className="h-4 w-4" />}
                            {isSending ? "Sending..." : "Send Bulk Message"}
                        </Button>

                        {result ? (
                            <div className="rounded-2xl border border-border bg-muted/30 p-4 text-sm">
                                <p className="font-semibold text-slate-900">Last Send Result</p>
                                <p className="mt-2 text-emerald-700">Success: {result.success_count}</p>
                                <p className="text-rose-700">Failed: {result.failed_count}</p>
                                {result.success_count > 0 ? (
                                    <p className="mt-3 text-xs text-slate-600">
                                        Provider accepted the successful messages. If the recipient still did not get them,
                                        check Meta webhook status, recipient eligibility, and 24-hour session/template rules.
                                    </p>
                                ) : null}
                                {result.results.length > 0 ? (
                                    <div className="mt-3 max-h-64 overflow-auto rounded-xl border border-border bg-white">
                                        <Table>
                                            <TableHeader>
                                                <TableRow>
                                                    <TableHead>Contact</TableHead>
                                                    <TableHead>Status</TableHead>
                                                    <TableHead>Message ID / Error</TableHead>
                                                </TableRow>
                                            </TableHeader>
                                            <TableBody>
                                                {result.results.map((item) => {
                                                    const contact = contactsById.get(item.contact_id);
                                                    const displayName = contact?.name ?? `Contact #${item.contact_id}`;
                                                    const statusLabel = item.status === "accepted" ? "Accepted" : "Failed";
                                                    const deliveryHint = explainDeliveryError(item.error);

                                                    return (
                                                        <TableRow key={`${item.contact_id}-${item.phone ?? "none"}`}>
                                                            <TableCell className="font-medium text-slate-900">{displayName}</TableCell>
                                                            <TableCell className={item.status === "accepted" ? "text-emerald-700" : "text-rose-700"}>
                                                                {statusLabel}
                                                            </TableCell>
                                                            <TableCell className="text-slate-600">
                                                                {item.message_id ? (
                                                                    item.message_id
                                                                ) : (
                                                                    <div className="space-y-1">
                                                                        <p>{item.error ?? "-"}</p>
                                                                        {deliveryHint ? <p className="text-xs text-amber-700">{deliveryHint}</p> : null}
                                                                    </div>
                                                                )}
                                                            </TableCell>
                                                        </TableRow>
                                                    );
                                                })}
                                            </TableBody>
                                        </Table>
                                    </div>
                                ) : null}
                            </div>
                        ) : null}

                        {errorMessage ? <p className="text-sm text-rose-700">{errorMessage}</p> : null}
                    </CardContent>
                </Card>
            </div>

            <Card>
                <CardHeader className="gap-4 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                        <CardTitle>Choose Contacts</CardTitle>
                        <CardDescription>Multi-select recipients for this campaign.</CardDescription>
                    </div>
                    <Input
                        value={search}
                        onChange={(event) => {
                            setSearch(event.target.value);
                            setCurrentPage(1);
                        }}
                        placeholder="Search by name or phone"
                        className="max-w-xs"
                    />
                </CardHeader>
                <CardContent>
                    <Table>
                        <TableHeader>
                            <TableRow>
                                <TableHead className="w-12">
                                    <input
                                        type="checkbox"
                                        aria-label="Select all current page contacts"
                                        checked={visibleContacts.length > 0 && selectedOnPageCount === visibleContacts.length}
                                        onChange={toggleSelectCurrentPage}
                                        className="h-4 w-4 rounded border-border"
                                    />
                                </TableHead>
                                <TableHead>Name</TableHead>
                                <TableHead>Phone</TableHead>
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {loadingContacts ? (
                                <TableRow>
                                    <TableCell colSpan={3} className="text-center text-muted-foreground">
                                        Loading contacts...
                                    </TableCell>
                                </TableRow>
                            ) : null}
                            {!loadingContacts && visibleContacts.length === 0 ? (
                                <TableRow>
                                    <TableCell colSpan={3} className="text-center text-muted-foreground">
                                        No contacts found. Add contacts from the Contacts page first.
                                    </TableCell>
                                </TableRow>
                            ) : (
                                visibleContacts.map((contact) => (
                                    <TableRow key={contact.id}>
                                        <TableCell>
                                            <input
                                                type="checkbox"
                                                aria-label={`Select ${contact.name}`}
                                                checked={selectedContactIds.includes(contact.id)}
                                                onChange={() => toggleContact(contact.id)}
                                                className="h-4 w-4 rounded border-border"
                                            />
                                        </TableCell>
                                        <TableCell className="font-medium text-slate-900">{contact.name}</TableCell>
                                        <TableCell className="text-slate-600">{contact.phone}</TableCell>
                                    </TableRow>
                                ))
                            )}
                        </TableBody>
                    </Table>

                    <div className="mt-4 flex items-center justify-between">
                        <p className="text-sm text-muted-foreground">
                            Page {safePage} of {totalPages}
                        </p>
                        <div className="flex gap-2">
                            <Button
                                variant="outline"
                                size="sm"
                                onClick={() => setCurrentPage((prev) => Math.max(1, prev - 1))}
                                disabled={safePage === 1}
                            >
                                Previous
                            </Button>
                            <Button
                                variant="outline"
                                size="sm"
                                onClick={() => setCurrentPage((prev) => Math.min(totalPages, prev + 1))}
                                disabled={safePage >= totalPages}
                            >
                                Next
                            </Button>
                        </div>
                    </div>
                </CardContent>
            </Card>
        </div>
    );
}
