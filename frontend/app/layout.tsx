import type { Metadata } from "next";
import { Manrope, Space_Grotesk } from "next/font/google";

import "./globals.css";
import { RootProvider } from "@/providers/root-provider";

const manrope = Manrope({
    subsets: ["latin"],
    variable: "--font-manrope",
});

const spaceGrotesk = Space_Grotesk({
    subsets: ["latin"],
    variable: "--font-space-grotesk",
});

export const metadata: Metadata = {
    title: "ChatPulse - Bulk Messaging Platform",
    description: "Professional bulk messaging and communication management platform",
};

export default function RootLayout({
    children,
}: Readonly<{
    children: React.ReactNode;
}>) {
    return (
        <html lang="en" suppressHydrationWarning>
            <body className={`${manrope.variable} ${spaceGrotesk.variable} font-[var(--font-manrope)]`}>
                <RootProvider>
                    {children}
                </RootProvider>
            </body>
        </html>
    );
}
