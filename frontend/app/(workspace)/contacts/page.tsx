import { Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

const contacts = [
    { id: 1, name: "Rhea Lawson", phone: "+14155550101", tags: ["Lead", "West"] },
    { id: 2, name: "Jonah Patel", phone: "+14155550102", tags: ["Customer"] },
    { id: 3, name: "Mina Chen", phone: "+14155550103", tags: ["Trial", "Priority"] },
    { id: 4, name: "Avery Brown", phone: "+14155550104", tags: ["Lead"] },
];

export default function ContactsPage() {
    return (
        <div className="space-y-6">
            <section className="flex flex-col justify-between gap-4 rounded-3xl border border-border/70 bg-white/80 p-6 shadow-soft sm:flex-row sm:items-center">
                <div>
                    <p className="text-xs font-semibold uppercase tracking-[0.22em] text-sky-700">Contacts</p>
                    <h2 className="mt-2 font-[var(--font-space-grotesk)] text-3xl font-semibold">Audience Directory</h2>
                    <p className="mt-2 text-sm text-muted-foreground">Import and segment your recipients before launching campaigns.</p>
                </div>
                <Button className="gap-2 self-start sm:self-auto">
                    <Plus className="h-4 w-4" />
                    Add Contact
                </Button>
            </section>

            <section className="grid gap-4 md:grid-cols-2">
                {contacts.map((contact) => (
                    <Card key={contact.id}>
                        <CardHeader>
                            <CardTitle className="text-xl">{contact.name}</CardTitle>
                            <CardDescription>{contact.phone}</CardDescription>
                        </CardHeader>
                        <CardContent className="flex flex-wrap gap-2">
                            {contact.tags.map((tag) => (
                                <span
                                    key={tag}
                                    className="rounded-full bg-sky-100 px-3 py-1 text-xs font-medium text-sky-900"
                                >
                                    {tag}
                                </span>
                            ))}
                        </CardContent>
                    </Card>
                ))}
            </section>
        </div>
    );
}
