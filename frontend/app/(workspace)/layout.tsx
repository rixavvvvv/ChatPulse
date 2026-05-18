"use client";

import { AppLayout } from "@/components/layout/app-layout";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/stores/auth";
import { getSession } from "@/lib/session";

export default function WorkspaceLayout({
    children,
}: Readonly<{
    children: React.ReactNode;
}>) {
    const router = useRouter();
    const { isAuthenticated, setAuthenticated } = useAuthStore();
    const [ready, setReady] = useState(false);

    useEffect(() => {
        const session = getSession();
        if (session) {
            setAuthenticated(true);
        } else {
            setAuthenticated(false);
            router.push("/login");
        }
        setReady(true);
    }, [router, setAuthenticated]);

    if (!ready || !isAuthenticated) {
        return null;
    }

    return <AppLayout>{children}</AppLayout>;
}
