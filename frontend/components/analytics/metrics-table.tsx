import React from "react";
import { cn } from "@/lib/utils";

interface Column<T> {
    key: string;
    header: string;
    render?: (row: T) => React.ReactNode;
}

interface MetricsTableProps<T> {
    columns: Column<T>[];
    data: T[];
    emptyText?: string;
}

export function MetricsTable<T>({ columns, data, emptyText = "No data" }: MetricsTableProps<T>) {
    return (
        <div className="rounded-xl border border-gray-200 dark:border-gray-800 overflow-hidden">
            <table className="w-full text-sm">
                <thead className="bg-gray-50 dark:bg-gray-900">
                    <tr>
                        {columns.map((col) => (
                            <th key={col.key} className="text-left px-4 py-3 text-xs font-semibold text-gray-500">
                                {col.header}
                            </th>
                        ))}
                    </tr>
                </thead>
                <tbody>
                    {data.length === 0 && (
                        <tr>
                            <td colSpan={columns.length} className="px-4 py-6 text-center text-gray-500">
                                {emptyText}
                            </td>
                        </tr>
                    )}
                    {data.map((row, idx) => (
                        <tr key={idx} className={cn("border-t border-gray-200 dark:border-gray-800")}> 
                            {columns.map((col) => (
                                <td key={col.key} className="px-4 py-3">
                                    {col.render ? col.render(row) : (row as any)[col.key]}
                                </td>
                            ))}
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}
