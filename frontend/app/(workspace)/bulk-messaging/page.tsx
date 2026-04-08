"use client";

import { useMemo, useState } from "react";
import { Loader2, SendHorizonal } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

type Contact = {
    id: number;
    name: string;
    phone: string;
};

type BulkSendResult = {
    success_count: number;
    failed_count: number;
};

const contacts: Contact[] = [
    { id: 1, name: "Rhea Lawson", phone: "+14155550101" },
    { id: 2, name: "Jonah Patel", phone: "+14155550102" },
    { id: 3, name: "Mina Chen", phone: "+14155550103" },
    { id: 4, name: "Avery Brown", phone: "+14155550104" },
    { id: 5, name: "Eli Turner", phone: "+14155550105" },
    { id: 6, name: "Sora Kim", phone: "+14155550106" },
    { id: 7, name: "Luca Diaz", phone: "+14155550107" },
    { id: 8, name: "Nina Roy", phone: "+14155550108" },
    { id: 9, name: "Arjun Shah", phone: "+14155550109" },
    { id: 10, name: "Noah White", phone: "+14155550110" },
];

const PAGE_SIZE = 5;

function previewMessage(template: string, name: string) {
    return template.replace(/\{\{\s*name\s*\}\}/gi, name);
}

export default function BulkMessagingPage() {
    const [messageTemplate, setMessageTemplate] = useState(
        "Hi {{name}}, just checking in with your latest update.",
    );
    const [search, setSearch] = useState("");
    const [currentPage, setCurrentPage] = useState(1);
    const [selectedContactIds, setSelectedContactIds] = useState<number[]>([]);
    const [isSending, setIsSending] = useState(false);
    const [result, setResult] = useState<BulkSendResult | null>(null);
    const [errorMessage, setErrorMessage] = useState<string | null>(null);

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
    }, [search]);

    const totalPages = Math.max(1, Math.ceil(filteredContacts.length / PAGE_SIZE));
    const safePage = Math.min(currentPage, totalPages);

    const visibleContacts = useMemo(() => {
        const start = (safePage - 1) * PAGE_SIZE;
        return filteredContacts.slice(start, start + PAGE_SIZE);
    }, [filteredContacts, safePage]);

    const selectedOnPageCount = visibleContacts.filter((contact) => selectedContactIds.includes(contact.id)).length;
    const selectedPreviewContact = contacts.find((contact) => contact.id === selectedContactIds[0]) ?? filteredContacts[0] ?? null;

    const previewText = previewMessage(messageTemplate, selectedPreviewContact?.name ?? "Contact");

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

        setIsSending(true);
        setErrorMessage(null);

        try {
            const response = await fetch(
                `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/bulk-send`,
                {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                    },
                    body: JSON.stringify({
                        message_template: messageTemplate,
                        contact_ids: selectedContactIds,
                    }),
                },
            );

            if (!response.ok) {
                throw new Error("Request failed");
            }

            const data: Partial<BulkSendResult> = await response.json();
            setResult({
                success_count: data.success_count ?? 0,
                failed_count: data.failed_count ?? 0,
            });
        } catch {
            setResult({ success_count: 0, failed_count: selectedContactIds.length });
            setErrorMessage("Backend is unavailable. Result shown as failed for selected contacts.");
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
                    Write a reusable template, pick recipients, preview personalization, and send in one flow.
                </p>
            </section>

            <div className="grid gap-6 xl:grid-cols-[1.2fr_1fr]">
                <Card>
                    <CardHeader>
                        <CardTitle>Message Template</CardTitle>
                        <CardDescription>Use variables like {"{{name}}"} to personalize each message.</CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                        <textarea
                            value={messageTemplate}
                            onChange={(event) => setMessageTemplate(event.target.value)}
                            className="min-h-36 w-full rounded-2xl border border-input bg-background px-4 py-3 text-sm outline-none ring-offset-background focus-visible:ring-2 focus-visible:ring-ring"
                            placeholder="Type your campaign message"
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
                        <Button onClick={handleSend} className="w-full gap-2" disabled={isSending || !messageTemplate.trim()}>
                            {isSending ? <Loader2 className="h-4 w-4 animate-spin" /> : <SendHorizonal className="h-4 w-4" />}
                            {isSending ? "Sending..." : "Send Bulk Message"}
                        </Button>

                        {result ? (
                            <div className="rounded-2xl border border-border bg-muted/30 p-4 text-sm">
                                <p className="font-semibold text-slate-900">Last Send Result</p>
                                <p className="mt-2 text-emerald-700">Success: {result.success_count}</p>
                                <p className="text-rose-700">Failed: {result.failed_count}</p>
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
                            {visibleContacts.length === 0 ? (
                                <TableRow>
                                    <TableCell colSpan={3} className="text-center text-muted-foreground">
                                        No contacts found.
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
