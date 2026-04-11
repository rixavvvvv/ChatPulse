"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { Plus, Upload } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { apiRequest } from "@/lib/api";
import { getSession } from "@/lib/session";

type Contact = {
    id: number;
    name: string;
    phone: string;
    tags: string[];
    created_at: string;
};

type ContactUploadResponse = {
    contacts_added: number;
    contacts_skipped: number;
};

export default function ContactsPage() {
    const [contacts, setContacts] = useState<Contact[]>([]);
    const [name, setName] = useState("");
    const [phone, setPhone] = useState("");
    const [csvFile, setCsvFile] = useState<File | null>(null);
    const [loading, setLoading] = useState(true);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [success, setSuccess] = useState<string | null>(null);

    const loadContacts = useCallback(async () => {
        const session = getSession();
        if (!session) {
            setLoading(false);
            setError("Login required to load contacts");
            return;
        }

        try {
            const payload = await apiRequest<Contact[]>("/contacts", {}, session.access_token);
            setContacts(payload);
        } catch (err) {
            setError(err instanceof Error ? err.message : "Unable to load contacts");
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        void loadContacts();
    }, [loadContacts]);

    async function handleAddContact(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        const session = getSession();
        if (!session) {
            setError("Login required to add contacts");
            return;
        }

        setBusy(true);
        setError(null);
        setSuccess(null);

        try {
            await apiRequest<Contact>(
                "/contacts",
                {
                    method: "POST",
                    body: JSON.stringify({
                        name,
                        phone,
                        tags: [],
                    }),
                },
                session.access_token,
            );
            setName("");
            setPhone("");
            setSuccess("Contact added");
            await loadContacts();
        } catch (err) {
            setError(err instanceof Error ? err.message : "Unable to add contact");
        } finally {
            setBusy(false);
        }
    }

    async function handleCsvUpload(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        const session = getSession();
        if (!session) {
            setError("Login required to upload contacts");
            return;
        }
        if (!csvFile) {
            setError("Select a CSV file first");
            return;
        }

        const formData = new FormData();
        formData.append("file", csvFile);

        setBusy(true);
        setError(null);
        setSuccess(null);

        try {
            const result = await apiRequest<ContactUploadResponse>(
                "/contacts/upload-csv",
                {
                    method: "POST",
                    body: formData,
                },
                session.access_token,
            );
            setCsvFile(null);
            setSuccess(`CSV processed: ${result.contacts_added} added, ${result.contacts_skipped} skipped`);
            await loadContacts();
        } catch (err) {
            setError(err instanceof Error ? err.message : "Unable to upload CSV");
        } finally {
            setBusy(false);
        }
    }

    return (
        <div className="space-y-6">
            <section className="flex flex-col justify-between gap-4 rounded-3xl border border-border/70 bg-white/80 p-6 shadow-soft sm:flex-row sm:items-center">
                <div>
                    <p className="text-xs font-semibold uppercase tracking-[0.22em] text-sky-700">Contacts</p>
                    <h2 className="mt-2 font-[var(--font-space-grotesk)] text-3xl font-semibold">Audience Directory</h2>
                    <p className="mt-2 text-sm text-muted-foreground">Import and segment your recipients before launching campaigns.</p>
                </div>
            </section>

            <div className="grid gap-6 lg:grid-cols-2">
                <Card>
                    <CardHeader>
                        <CardTitle className="flex items-center gap-2 text-xl">
                            <Plus className="h-4 w-4" />
                            Add Contact
                        </CardTitle>
                        <CardDescription>Add a single recipient to the active workspace.</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <form className="space-y-3" onSubmit={handleAddContact}>
                            <Input
                                placeholder="Name"
                                value={name}
                                onChange={(event) => setName(event.target.value)}
                                required
                            />
                            <Input
                                placeholder="Phone (+14155550101)"
                                value={phone}
                                onChange={(event) => setPhone(event.target.value)}
                                required
                            />
                            <Button type="submit" disabled={busy || loading}>Add Contact</Button>
                        </form>
                    </CardContent>
                </Card>

                <Card>
                    <CardHeader>
                        <CardTitle className="flex items-center gap-2 text-xl">
                            <Upload className="h-4 w-4" />
                            Upload CSV
                        </CardTitle>
                        <CardDescription>CSV must include headers: name,phone.</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <form className="space-y-3" onSubmit={handleCsvUpload}>
                            <Input
                                type="file"
                                accept=".csv,text/csv"
                                onChange={(event) => setCsvFile(event.target.files?.[0] ?? null)}
                                required
                            />
                            <Button type="submit" disabled={busy || loading}>Upload Contacts CSV</Button>
                        </form>
                    </CardContent>
                </Card>
            </div>

            {loading ? <p className="text-sm text-muted-foreground">Loading contacts...</p> : null}
            {error ? <p className="text-sm text-rose-700">{error}</p> : null}
            {success ? <p className="text-sm text-emerald-700">{success}</p> : null}

            <section className="grid gap-4 md:grid-cols-2">
                {contacts.length === 0 && !loading ? (
                    <Card>
                        <CardContent className="pt-6 text-sm text-muted-foreground">
                            No contacts in this workspace yet.
                        </CardContent>
                    </Card>
                ) : null}
                {contacts.map((contact) => (
                    <Card key={contact.id}>
                        <CardHeader>
                            <CardTitle className="text-xl">{contact.name}</CardTitle>
                            <CardDescription>{contact.phone}</CardDescription>
                        </CardHeader>
                        <CardContent className="flex flex-wrap gap-2">
                            {contact.tags.length === 0 ? (
                                <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-700">
                                    No tags
                                </span>
                            ) : (
                                contact.tags.map((tag) => (
                                    <span
                                        key={tag}
                                        className="rounded-full bg-sky-100 px-3 py-1 text-xs font-medium text-sky-900"
                                    >
                                        {tag}
                                    </span>
                                ))
                            )}
                        </CardContent>
                    </Card>
                ))}
            </section>
        </div>
    );
}
