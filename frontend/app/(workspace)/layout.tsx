import Link from "next/link";
import { Menu, Search } from "lucide-react";

import { SidebarNav } from "@/components/sidebar-nav";

export default function WorkspaceLayout({
    children,
}: Readonly<{
    children: React.ReactNode;
}>) {
    return (
        <div className="min-h-screen">
            <SidebarNav />

            <header className="sticky top-0 z-10 hidden border-b border-border/60 bg-white/75 backdrop-blur md:block md:pl-72">
                <div className="container flex items-center justify-between py-4">
                    <div className="flex w-full max-w-md items-center gap-2 rounded-xl border border-border/80 bg-white px-3 py-2">
                        <Search className="h-4 w-4 text-slate-500" />
                        <input
                            aria-label="Search"
                            placeholder="Search contacts, campaigns..."
                            className="w-full bg-transparent text-sm outline-none placeholder:text-slate-400"
                        />
                    </div>

                    <div className="ml-6 flex items-center gap-3">
                        <div className="text-right">
                            <p className="text-sm font-semibold text-slate-900">Ava Morrison</p>
                            <p className="text-xs text-slate-500">Operations Lead</p>
                        </div>
                        <div className="flex h-10 w-10 items-center justify-center rounded-full border border-sky-200 bg-sky-100 font-semibold text-sky-900">
                            AM
                        </div>
                    </div>
                </div>
            </header>

            <header className="sticky top-0 z-10 border-b border-border/60 bg-white/70 backdrop-blur md:hidden">
                <div className="container flex items-center justify-between py-4">
                    <p className="font-[var(--font-space-grotesk)] text-lg font-semibold">Bulk Messaging</p>
                    <div className="flex items-center gap-2">
                        <Link href="/dashboard" className="rounded-lg px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100">
                            Dashboard
                        </Link>
                        <Link href="/contacts" className="rounded-lg px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100">
                            Contacts
                        </Link>
                        <Link href="/bulk-messaging" className="rounded-lg px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100">
                            Bulk
                        </Link>
                        <span className="rounded-lg border border-border p-2 text-slate-600">
                            <Menu className="h-4 w-4" />
                        </span>
                    </div>
                </div>
            </header>

            <div className="md:pl-72">
                <main className="container py-8 md:py-10">{children}</main>
            </div>
        </div>
    );
}
