import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

export default function LoginPage() {
    return (
        <main className="relative flex min-h-screen items-center justify-center p-6">
            <div className="pointer-events-none absolute inset-0 bg-grid bg-[size:36px_36px] opacity-40" />

            <Card className="relative z-10 w-full max-w-md border-white/70 bg-white/85">
                <CardHeader className="space-y-3">
                    <p className="text-xs font-semibold uppercase tracking-[0.24em] text-sky-700">Welcome Back</p>
                    <CardTitle className="font-[var(--font-space-grotesk)] text-3xl">Log In</CardTitle>
                    <CardDescription>Manage campaigns and monitor message delivery in one place.</CardDescription>
                </CardHeader>
                <CardContent>
                    <form className="space-y-4">
                        <div className="space-y-2">
                            <label htmlFor="email" className="text-sm font-medium text-slate-700">
                                Email
                            </label>
                            <Input id="email" type="email" placeholder="you@company.com" />
                        </div>
                        <div className="space-y-2">
                            <label htmlFor="password" className="text-sm font-medium text-slate-700">
                                Password
                            </label>
                            <Input id="password" type="password" placeholder="Enter your password" />
                        </div>
                        <Button className="w-full" size="lg" type="submit">
                            Continue
                        </Button>
                    </form>

                    <div className="mt-5 text-center text-sm text-muted-foreground">
                        Demo flow enabled. Continue to the dashboard.
                        <Link href="/dashboard" className="ml-1 font-medium text-sky-700 hover:text-sky-900">
                            Open app
                        </Link>
                    </div>
                </CardContent>
            </Card>
        </main>
    );
}
