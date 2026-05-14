import React from "react";
import {
    useReactTable,
    getCoreRowModel,
    flexRender,
    ColumnDef,
    Row,
} from "@tanstack/react-table";
import { cn } from "@/lib/utils";
import { Checkbox } from "./checkbox";

export interface DataTableProps<TData, TValue> {
    columns: ColumnDef<TData, TValue>[];
    data: TData[];
    isLoading?: boolean;
    onRowClick?: (row: Row<TData>) => void;
    selectedRows?: Set<string | number>;
    onRowSelect?: (id: string | number, selected: boolean) => void;
    enableSelection?: boolean;
}

export function DataTable<TData extends { id?: string | number }, TValue>({
    columns,
    data,
    isLoading = false,
    onRowClick,
    selectedRows,
    onRowSelect,
    enableSelection = false,
}: DataTableProps<TData, TValue>) {
    const table = useReactTable({
        data,
        columns: enableSelection
            ? [
                {
                    id: "select",
                    header: ({ table }) => (
                        <Checkbox
                            checked={table.getIsAllRowsSelected()}
                            indeterminate={table.getIsSomeRowsSelected()}
                            onChange={table.getToggleAllRowsSelectedHandler()}
                        />
                    ),
                    cell: ({ row }) => (
                        <Checkbox
                            checked={row.getIsSelected()}
                            onChange={row.getToggleSelectedHandler()}
                        />
                    ),
                    size: 50,
                },
                ...columns,
            ]
            : columns,
        getCoreRowModel: getCoreRowModel(),
    });

    return (
        <div className="border border-gray-200 dark:border-gray-800 rounded-lg overflow-hidden">
            <table className="w-full">
                <thead className="bg-gray-50 dark:bg-gray-900 border-b border-gray-200 dark:border-gray-800">
                    {table.getHeaderGroups().map((headerGroup) => (
                        <tr key={headerGroup.id}>
                            {headerGroup.headers.map((header) => (
                                <th
                                    key={header.id}
                                    className="px-6 py-3 text-left text-sm font-semibold text-gray-700 dark:text-gray-300"
                                    style={{
                                        width:
                                            header.getSize() === 150
                                                ? "auto"
                                                : `${header.getSize()}px`,
                                    }}
                                >
                                    {header.isPlaceholder
                                        ? null
                                        : flexRender(header.column.columnDef.header, header.getContext())}
                                </th>
                            ))}
                        </tr>
                    ))}
                </thead>

                <tbody>
                    {isLoading ? (
                        <tr>
                            <td colSpan={columns.length} className="px-6 py-12 text-center">
                                <div className="flex justify-center">
                                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" />
                                </div>
                            </td>
                        </tr>
                    ) : data.length === 0 ? (
                        <tr>
                            <td colSpan={columns.length} className="px-6 py-12 text-center text-gray-600 dark:text-gray-400">
                                No data available
                            </td>
                        </tr>
                    ) : (
                        table.getRowModel().rows.map((row) => (
                            <tr
                                key={row.id}
                                className={cn(
                                    "border-b border-gray-200 dark:border-gray-800 transition-colors",
                                    onRowClick && "cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800",
                                    selectedRows?.has(row.original.id as string | number) &&
                                    "bg-blue-50 dark:bg-blue-950"
                                )}
                                onClick={() => onRowClick?.(row)}
                            >
                                {row.getVisibleCells().map((cell) => (
                                    <td
                                        key={cell.id}
                                        className="px-6 py-4 text-sm text-gray-900 dark:text-gray-100"
                                    >
                                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                                    </td>
                                ))}
                            </tr>
                        ))
                    )}
                </tbody>
            </table>
        </div>
    );
}
