"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useUIStore } from "@/stores/ui";
import { cn } from "@/lib/utils";
import {
    LayoutDashboard,
    Inbox,
    Send,
    Users,
    Zap,
    BarChart3,
    Workflow,
    Cog,
    X,
    Shield,
} from "lucide-react";

const navigationItems = [
    { label: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
    { label: "Inbox", href: "/inbox", icon: Inbox },
    { label: "Campaigns", href: "/campaigns", icon: Send },
    { label: "Contacts", href: "/contacts", icon: Users },
    { label: "Segments", href: "/segments", icon: Zap },
    { label: "Workflows", href: "/workflows", icon: Workflow },
    { label: "Analytics", href: "/analytics", icon: BarChart3 },
    { label: "Automations", href: "/automations", icon: Zap },
    { label: "Settings", href: "/settings", icon: Cog },
    { label: "Admin", href: "/admin", icon: Shield },
];

export function Sidebar() {
    const pathname = usePathname();
    const { sidebarOpen, toggleSidebar } = useUIStore();

    return (
        <>
            {/* Mobile backdrop */}
            {sidebarOpen && (
                <div
                    className="fixed inset-0 z-30 bg-black bg-opacity-50 md:hidden"
                    onClick={toggleSidebar}
                />
            )}

            {/* Sidebar */}
            <aside
                className={cn(
                    "fixed left-0 top-0 h-screen w-64 border-r border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-950 transition-transform duration-300 z-40 pt-16 overflow-y-auto md:translate-x-0 md:relative md:pt-0",
                    sidebarOpen ? "translate-x-0" : "-translate-x-full"
                )}
            >
                {/* Close button for mobile */}
                <button
                    onClick={toggleSidebar}
                    className="absolute top-4 right-4 md:hidden p-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg"
                >
                    <X size={20} />
                </button>

                {/* Navigation */}
                <nav className="px-4 py-6 md:p-6 space-y-2">
                    {navigationItems.map((item) => {
                        const Icon = item.icon;
                        const isActive = pathname.startsWith(item.href);

                        return (
                            <Link
                                key={item.href}
                                href={item.href}
                                onClick={() => {
                                    // Close sidebar on mobile after navigation
                                    if (window.innerWidth < 768) {
                                        toggleSidebar();
                                    }
                                }}
                                className={cn(
                                    "flex items-center gap-3 px-4 py-2 rounded-lg transition-colors",
                                    isActive
                                        ? "bg-blue-100 dark:bg-blue-950 text-blue-700 dark:text-blue-200 font-semibold"
                                        : "text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800"
                                )}
                            >
                                <Icon size={20} />
                                <span>{item.label}</span>
                            </Link>
                        );
                    })}
                </nav>
            </aside>
        </>
    );
}
