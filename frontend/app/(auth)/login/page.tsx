"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { apiRequest } from "@/lib/api";
import { saveSession } from "@/lib/session";

type LoginResponse = {
    access_token: string;
    token_type: string;
    workspace_id: number;
    role: string;
};

export default function LoginPage() {
    const router = useRouter();
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    async function handleSubmit(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        setLoading(true);
        setError(null);

        try {
            const payload = await apiRequest<LoginResponse>("/auth/login", {
                method: "POST",
                body: JSON.stringify({
                    email,
                    password,
                }),
            });

            saveSession({
                access_token: payload.access_token,
                workspace_id: payload.workspace_id,
                role: payload.role,
            });

            router.push("/dashboard");
        } catch (err) {
            setError(err instanceof Error ? err.message : "Unable to log in");
        } finally {
            setLoading(false);
        }
    }

    return (
        <main className="relative flex min-h-screen items-center justify-center p-6">
            <div className="pointer-events-none absolute inset-0 bg-grid bg-[size:36px_36px] opacity-40" />

            <Card className="relative z-10 w-full max-w-md border-white/70 bg-white/85">
                <CardHeader className="space-y-3">
                    <p className="text-xs font-semibold uppercase tracking-[0.24em] text-sky-700">Welcome Back</p>
                    <CardTitle className="font-[var(--font-space-grotesk)] text-3xl">Log In</CardTitle>
                    <CardDescription>Use your API credentials to enter the operational workspace.</CardDescription>
                </CardHeader>
                <CardContent>
                    <form className="space-y-4" onSubmit={handleSubmit}>
                        <div className="space-y-2">
                            <label htmlFor="email" className="text-sm font-medium text-slate-700">
                                Email
                            </label>
                            <Input
                                id="email"
                                type="email"
                                placeholder="you@company.com"
                                value={email}
                                onChange={(event) => setEmail(event.target.value)}
                                required
                            />
                        </div>
                        <div className="space-y-2">
                            <label htmlFor="password" className="text-sm font-medium text-slate-700">
                                Password
                            </label>
                            <Input
                                id="password"
                                type="password"
                                placeholder="Enter your password"
                                value={password}
                                onChange={(event) => setPassword(event.target.value)}
                                required
                            />
                        </div>
                        <Button className="w-full" size="lg" type="submit" disabled={loading}>
                            {loading ? "Signing In..." : "Continue"}
                        </Button>
                    </form>

                    {error ? <p className="mt-4 text-sm text-rose-700">{error}</p> : null}
                </CardContent>
            </Card>
        </main>
    );
}
