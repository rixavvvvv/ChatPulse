import React from "react";
import { ChevronRight } from "lucide-react";

export interface PageLayoutProps {
    title: string;
    description?: string;
    breadcrumbs?: Array<{ label: string; href?: string }>;
    actions?: React.ReactNode;
    children: React.ReactNode;
}

export function PageLayout({
    title,
    description,
    breadcrumbs,
    actions,
    children,
}: PageLayoutProps) {
    return (
        <div className="space-y-6">
            {/* Breadcrumbs */}
            {breadcrumbs && breadcrumbs.length > 0 && (
                <div className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400">
                    {breadcrumbs.map((crumb, index) => (
                        <div key={index} className="flex items-center gap-2">
                            {index > 0 && <ChevronRight size={16} />}
                            {crumb.href ? (
                                <a href={crumb.href} className="hover:text-gray-900 dark:hover:text-gray-200">
                                    {crumb.label}
                                </a>
                            ) : (
                                <span>{crumb.label}</span>
                            )}
                        </div>
                    ))}
                </div>
            )}

            {/* Header */}
            <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
                <div>
                    <h1 className="text-3xl font-bold">{title}</h1>
                    {description && <p className="text-gray-600 dark:text-gray-400 mt-1">{description}</p>}
                </div>

                {actions && <div className="flex items-center gap-3">{actions}</div>}
            </div>

            {/* Content */}
            <div>{children}</div>
        </div>
    );
}
