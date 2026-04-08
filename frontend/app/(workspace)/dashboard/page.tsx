import { ArrowUpRight, MessageSquareText, Users2 } from "lucide-react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

const metrics = [
    { label: "Messages Sent", value: "12,480", delta: "+11.8%", icon: MessageSquareText },
    { label: "Active Contacts", value: "3,204", delta: "+4.2%", icon: Users2 },
    { label: "Reply Rate", value: "27.4%", delta: "+2.1%", icon: ArrowUpRight },
];

export default function DashboardPage() {
    return (
        <div className="space-y-6">
            <section className="rounded-3xl border border-sky-100 bg-gradient-to-r from-sky-100/80 via-cyan-50 to-orange-50 p-8 shadow-soft">
                <p className="mb-2 text-xs font-semibold uppercase tracking-[0.22em] text-sky-700">Overview</p>
                <h2 className="font-[var(--font-space-grotesk)] text-3xl font-semibold text-slate-900 md:text-4xl">
                    Message performance at a glance
                </h2>
                <p className="mt-3 max-w-2xl text-slate-700">
                    Track campaign health, monitor replies, and keep outreach quality high with concise personalized templates.
                </p>
            </section>

            <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
                {metrics.map((item) => (
                    <Card key={item.label}>
                        <CardHeader className="flex flex-row items-center justify-between space-y-0">
                            <CardDescription>{item.label}</CardDescription>
                            <item.icon className="h-4 w-4 text-sky-700" />
                        </CardHeader>
                        <CardContent>
                            <CardTitle className="text-3xl">{item.value}</CardTitle>
                            <p className="mt-2 text-sm text-emerald-700">{item.delta} from last week</p>
                        </CardContent>
                    </Card>
                ))}
            </section>
        </div>
    );
}
