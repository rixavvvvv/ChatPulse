import React from "react";
import { AlertCircle, RefreshCw } from "lucide-react";

export interface ErrorBoundaryProps {
    children: React.ReactNode;
    fallback?: React.ReactNode;
}

export interface ErrorBoundaryState {
    hasError: boolean;
    error?: Error;
}

export class ErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
    constructor(props: ErrorBoundaryProps) {
        super(props);
        this.state = { hasError: false };
    }

    static getDerivedStateFromError(error: Error): ErrorBoundaryState {
        return { hasError: true, error };
    }

    componentDidCatch(error: Error) {
        console.error("Error caught by boundary:", error);
    }

    render() {
        if (this.state.hasError) {
            return (
                this.props.fallback || (
                    <div className="flex flex-col items-center justify-center min-h-screen bg-gray-50 dark:bg-gray-900">
                        <AlertCircle className="mb-4 text-red-500" size={48} />
                        <h1 className="text-2xl font-bold mb-2">Something went wrong</h1>
                        <p className="text-gray-600 dark:text-gray-400 mb-4">
                            {this.state.error?.message}
                        </p>
                        <button
                            onClick={() => window.location.reload()}
                            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
                        >
                            <RefreshCw size={16} />
                            Reload page
                        </button>
                    </div>
                )
            );
        }

        return this.props.children;
    }
}

export function Loading({ text = "Loading..." }: { text?: string }) {
    return (
        <div className="flex flex-col items-center justify-center py-12">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mb-4" />
            <p className="text-gray-600 dark:text-gray-400">{text}</p>
        </div>
    );
}

export function EmptyState({
    title,
    description,
    icon: Icon,
    action,
}: {
    title: string;
    description?: string;
    icon?: React.ComponentType<{ size: number }>;
    action?: React.ReactNode;
}) {
    return (
        <div className="flex flex-col items-center justify-center py-12">
            {Icon && <Icon size={48} className="mb-4 text-gray-400" />}
            <h3 className="text-lg font-semibold mb-2">{title}</h3>
            {description && <p className="text-gray-600 dark:text-gray-400 mb-4">{description}</p>}
            {action && <div>{action}</div>}
        </div>
    );
}
