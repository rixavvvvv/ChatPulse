"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ContactRound, LayoutDashboard, Megaphone, Rocket, Workflow } from "lucide-react";

import { cn } from "@/lib/utils";

const navItems = [
    {
        href: "/dashboard",
        label: "Dashboard",
        icon: LayoutDashboard,
    },
    {
        href: "/onboarding",
        label: "Onboarding",
        icon: Rocket,
    },
    {
        href: "/contacts",
        label: "Contacts",
        icon: ContactRound,
    },
    {
        href: "/campaigns",
        label: "Campaign Builder",
        icon: Workflow,
    },
    {
        href: "/bulk-messaging",
        label: "Bulk Messaging",
        icon: Megaphone,
    },
];

export function SidebarNav() {
    const pathname = usePathname();

    return (
        <aside className="fixed inset-y-0 left-0 z-20 hidden w-72 border-r border-border/60 bg-white/75 px-5 py-6 backdrop-blur md:flex md:flex-col">
            <div className="mb-10 space-y-2">
                <p className="text-xs font-semibold uppercase tracking-[0.22em] text-sky-700">Bulk Messaging</p>
                <h1 className="text-2xl font-semibold">Control Center</h1>
            </div>

            <nav className="space-y-2">
                {navItems.map((item) => {
                    const isActive = pathname.startsWith(item.href);
                    return (
                        <Link
                            key={item.href}
                            href={item.href}
                            className={cn(
                                "flex items-center gap-3 rounded-xl px-4 py-3 text-sm font-medium transition",
                                isActive
                                    ? "bg-sky-100 text-sky-900"
                                    : "text-slate-700 hover:bg-slate-100 hover:text-slate-900",
                            )}
                        >
                            <item.icon className="h-4 w-4" />
                            {item.label}
                        </Link>
                    );
                })}
            </nav>

            <div className="mt-auto rounded-2xl border border-sky-200 bg-sky-50 p-4 text-sm text-sky-900">
                Keep your templates short and personalized for better response rates.
            </div>
        </aside>
    );
}
