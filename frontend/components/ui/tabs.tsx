"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

interface TabsContextValue {
    value: string;
    onValueChange: (value: string) => void;
}

const TabsContext = React.createContext<TabsContextValue | null>(null);

function useTabsContext() {
    const context = React.useContext(TabsContext);
    if (!context) {
        throw new Error("Tabs components must be used within a Tabs provider");
    }
    return context;
}

export interface TabsProps extends React.HTMLAttributes<HTMLDivElement> {
    value: string;
    onValueChange: (value: string) => void;
}

export function Tabs({ value, onValueChange, className, children, ...props }: TabsProps) {
    return (
        <TabsContext.Provider value={{ value, onValueChange }}>
            <div className={className} {...props}>
                {children}
            </div>
        </TabsContext.Provider>
    );
}

export function TabsList({ className, children, ...props }: React.HTMLAttributes<HTMLDivElement>) {
    return (
        <div className={cn("flex border-b border-border", className)} {...props}>
            {children}
        </div>
    );
}

export function TabsTrigger({ value: triggerValue, className, children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement> & { value: string }) {
    const { value: selectedValue, onValueChange } = useTabsContext();
    const isSelected = selectedValue === triggerValue;

    return (
        <button
            className={cn(
                "px-4 py-2 text-sm font-medium transition-colors relative flex items-center gap-2",
                isSelected
                    ? "text-foreground"
                    : "text-muted-foreground hover:text-foreground",
                className
            )}
            onClick={() => onValueChange(triggerValue)}
            {...props}
        >
            {children}
            {isSelected && (
                <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-primary" />
            )}
        </button>
    );
}

export function TabsContent({ value: contentValue, className, children, ...props }: React.HTMLAttributes<HTMLDivElement> & { value: string }) {
    const { value: selectedValue } = useTabsContext();

    if (selectedValue !== contentValue) {
        return null;
    }

    return (
        <div className={cn("pt-4", className)} {...props}>
            {children}
        </div>
    );
}

export interface SimpleTabsProps {
    tabs: Array<{
        label: string;
        value: string;
        icon?: React.ReactNode;
    }>;
    value: string;
    onChange: (value: string) => void;
}

export function SimpleTabs({ tabs, value, onChange }: SimpleTabsProps) {
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