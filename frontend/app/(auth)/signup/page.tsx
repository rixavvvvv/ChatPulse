"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
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

type SignupResponse = {
    id: number;
    email: string;
    role: string;
    subscription_plan: string;
    is_active: boolean;
};

export default function SignupPage() {
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
            await apiRequest<SignupResponse>("/auth/signup", {
                method: "POST",
                body: JSON.stringify({
                    email,
                    password,
                }),
            });

            const login = await apiRequest<LoginResponse>("/auth/login", {
                method: "POST",
                body: JSON.stringify({
                    email,
                    password,
                }),
            });

            saveSession({
                access_token: login.access_token,
                workspace_id: login.workspace_id,
                role: login.role,
            });

            router.push("/dashboard");
        } catch (err) {
            setError(err instanceof Error ? err.message : "Unable to sign up");
        } finally {
            setLoading(false);
        }
    }

    return (
        <main className="relative flex min-h-screen items-center justify-center p-6">
            <div className="pointer-events-none absolute inset-0 bg-grid bg-[size:36px_36px] opacity-40" />

            <Card className="relative z-10 w-full max-w-md border-white/70 bg-white/85">
                <CardHeader className="space-y-3">
                    <p className="text-xs font-semibold uppercase tracking-[0.24em] text-sky-700">New workspace</p>
                    <CardTitle className="font-[var(--font-space-grotesk)] text-3xl">Create account</CardTitle>
                    <CardDescription>Register once, then continue to onboarding and messaging.</CardDescription>
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
                                placeholder="At least 8 characters"
                                value={password}
                                onChange={(event) => setPassword(event.target.value)}
                                required
                                minLength={8}
                            />
                        </div>
                        <Button className="w-full" size="lg" type="submit" disabled={loading}>
                            {loading ? "Creating account..." : "Sign up"}
                        </Button>
                    </form>

                    {error ? <p className="mt-4 text-sm text-rose-700">{error}</p> : null}

                    <p className="mt-6 text-center text-sm text-slate-600">
                        Already registered?{" "}
                        <Link href="/login" className="font-medium text-sky-700 hover:underline">
                            Log in
                        </Link>
                    </p>
                </CardContent>
            </Card>
        </main>
    );
}
