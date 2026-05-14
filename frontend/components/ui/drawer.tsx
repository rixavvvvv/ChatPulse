import * as React from "react";
import { cn } from "@/lib/utils";
import { X } from "lucide-react";

export interface DrawerProps {
    isOpen: boolean;
    onClose: () => void;
    title?: string;
    children: React.ReactNode;
    position?: "left" | "right";
    size?: "sm" | "md" | "lg";
}

const sizes = {
    sm: "w-64",
    md: "w-96",
    lg: "w-full md:w-[500px]",
};

export function Drawer({
    isOpen,
    onClose,
    title,
    children,
    position = "right",
    size = "md",
}: DrawerProps) {
    if (!isOpen) return null;

    const positionClass = position === "left" ? "left-0" : "right-0";

    return (
        <div className="fixed inset-0 z-50 flex">
            {/* Backdrop */}
            <div
                className="absolute inset-0 bg-black bg-opacity-50 dark:bg-opacity-70"
                onClick={onClose}
            />

            {/* Drawer */}
            <div
                className={cn(
                    "relative bg-white dark:bg-gray-950 shadow-lg h-full overflow-y-auto transition-transform",
                    positionClass,
                    sizes[size]
                )}
            >
                {/* Header */}
                <div className="flex items-center justify-between p-6 border-b border-gray-200 dark:border-gray-800 sticky top-0 bg-white dark:bg-gray-950">
                    {title && <h2 className="text-lg font-semibold">{title}</h2>}
                    <button
                        onClick={onClose}
                        className="text-gray-500 hover:text-gray-700 dark:hover:text-gray-300 ml-auto"
                    >
                        <X size={20} />
                    </button>
                </div>

                {/* Content */}
                <div className="p-6">{children}</div>
            </div>
        </div>
    );
}
