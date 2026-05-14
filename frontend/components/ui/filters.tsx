import React, { useState } from "react";
import { X, Filter } from "lucide-react";
import { cn } from "@/lib/utils";

export interface FilterOption {
    label: string;
    value: string;
    count?: number;
}

export interface FilterConfig {
    label: string;
    key: string;
    options: FilterOption[];
    type?: "checkbox" | "radio";
}

export interface FiltersProps {
    filters: FilterConfig[];
    activeFilters: Record<string, string[]>;
    onFilterChange: (key: string, values: string[]) => void;
    onClear: () => void;
}

export function Filters({
    filters,
    activeFilters,
    onFilterChange,
    onClear,
}: FiltersProps) {
    const [isOpen, setIsOpen] = useState(false);

    const activeCount = Object.values(activeFilters).reduce(
        (sum, vals) => sum + vals.length,
        0
    );

    return (
        <div className="flex items-center gap-4">
            <button
                onClick={() => setIsOpen(!isOpen)}
                className={cn(
                    "flex items-center gap-2 px-4 py-2 rounded-lg border transition-colors",
                    isOpen
                        ? "bg-gray-100 dark:bg-gray-800 border-gray-300 dark:border-gray-700"
                        : "hover:bg-gray-50 dark:hover:bg-gray-900"
                )}
            >
                <Filter size={18} />
                <span>Filters</span>
                {activeCount > 0 && (
                    <span className="ml-2 px-2 py-1 text-xs bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-100 rounded-full">
                        {activeCount}
                    </span>
                )}
            </button>

            {activeCount > 0 && (
                <button
                    onClick={onClear}
                    className="text-sm text-blue-600 hover:text-blue-700 dark:hover:text-blue-400"
                >
                    Clear all
                </button>
            )}

            {isOpen && (
                <div className="absolute top-full left-0 mt-2 bg-white dark:bg-gray-950 border border-gray-200 dark:border-gray-800 rounded-lg shadow-lg p-4 z-10 min-w-64">
                    {filters.map((filter) => (
                        <div key={filter.key} className="mb-6 last:mb-0">
                            <h4 className="font-semibold text-sm mb-3">{filter.label}</h4>
                            <div className="space-y-2">
                                {filter.options.map((option) => (
                                    <label
                                        key={option.value}
                                        className="flex items-center gap-3 cursor-pointer"
                                    >
                                        <input
                                            type={filter.type || "checkbox"}
                                            name={filter.key}
                                            value={option.value}
                                            checked={activeFilters[filter.key]?.includes(option.value) || false}
                                            onChange={(e) => {
                                                const newValues = activeFilters[filter.key] || [];
                                                if (e.target.checked) {
                                                    onFilterChange(
                                                        filter.key,
                                                        filter.type === "radio"
                                                            ? [option.value]
                                                            : [...newValues, option.value]
                                                    );
                                                } else {
                                                    onFilterChange(
                                                        filter.key,
                                                        newValues.filter((v) => v !== option.value)
                                                    );
                                                }
                                            }}
                                            className="w-4 h-4 accent-blue-600"
                                        />
                                        <span className="text-sm flex-1">{option.label}</span>
                                        {option.count !== undefined && (
                                            <span className="text-xs text-gray-500">({option.count})</span>
                                        )}
                                    </label>
                                ))}
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}
