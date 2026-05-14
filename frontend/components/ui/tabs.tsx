import * as React from "react";
import { cn } from "@/lib/utils";

export interface TabsProps {
    tabs: Array<{
        label: string;
        value: string;
        icon?: React.ReactNode;
    }>;
    value: string;
    onChange: (value: string) => void;
}

export function Tabs({ tabs, value, onChange }: TabsProps) {
    return (
        <div className="border-b border-gray-200 dark:border-gray-800">
            <div className="flex gap-8 px-4">
                {tabs.map((tab) => (
                    <button
                        key={tab.value}
                        onClick={() => onChange(tab.value)}
                        className={cn(
                            "py-4 px-1 border-b-2 font-medium text-sm transition-colors whitespace-nowrap flex items-center gap-2",
                            value === tab.value
                                ? "border-blue-600 text-blue-600"
                                : "border-transparent text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200"
                        )}
                    >
                        {tab.icon && <span>{tab.icon}</span>}
                        {tab.label}
                    </button>
                ))}
            </div>
        </div>
    );
}
