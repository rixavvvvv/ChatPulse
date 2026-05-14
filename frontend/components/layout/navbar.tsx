"use client";

import React from "react";
import { useAuthStore } from "@/stores/auth";
import { useUIStore } from "@/stores/ui";
import { Menu, LogOut, Settings, Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import { generateInitials } from "@/lib/utils";
import Link from "next/link";

export function Navbar() {
    const { user, logout } = useAuthStore();
    const { toggleSidebar } = useUIStore();
    const { theme, setTheme } = useTheme();

    return (
        <nav className="sticky top-0 z-40 border-b border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-950 shadow-sm">
            <div className="flex items-center justify-between px-4 py-3 md:px-6">
                {/* Left: Menu + Logo */}
                <div className="flex items-center gap-4">
                    <button
                        onClick={toggleSidebar}
                        className="md:hidden p-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg"
                    >
                        <Menu size={20} />
                    </button>

                    <Link href="/" className="font-bold text-xl">
                        ChatPulse
                    </Link>
                </div>

                {/* Right: Theme toggle + User menu */}
                <div className="flex items-center gap-4">
                    <button
                        onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
                        className="p-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg"
                    >
                        {theme === "dark" ? <Sun size={20} /> : <Moon size={20} />}
                    </button>

                    {user && (
                        <div className="flex items-center gap-3">
                            <div className="w-8 h-8 rounded-full bg-blue-600 text-white flex items-center justify-center text-sm font-semibold">
                                {generateInitials(user.first_name, user.last_name)}
                            </div>

                            <div className="hidden md:block text-sm">
                                <p className="font-semibold">{user.first_name}</p>
                                <p className="text-gray-600 dark:text-gray-400">{user.email}</p>
                            </div>

                            <div className="flex gap-2 ml-2">
                                <Link
                                    href="/settings"
                                    className="p-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg"
                                    title="Settings"
                                >
                                    <Settings size={20} />
                                </Link>

                                <button
                                    onClick={() => logout()}
                                    className="p-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg text-red-600"
                                    title="Logout"
                                >
                                    <LogOut size={20} />
                                </button>
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </nav>
    );
}
