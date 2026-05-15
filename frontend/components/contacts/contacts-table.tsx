"use client";

import { useState, useMemo, useCallback } from "react";
import {
    useReactTable,
    getCoreRowModel,
    getSortedRowModel,
    getFilteredRowModel,
    getPaginationRowModel,
    flexRender,
    ColumnDef,
    SortingState,
    Row,
} from "@tanstack/react-table";
import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight, Loader2 } from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import type { Contact } from "@/lib/types/contact";
import { createContactsColumns } from "./columns";

export interface ContactsTableProps {
    data: Contact[];
    isLoading?: boolean;
    isError?: boolean;
    errorMessage?: string;
    onEdit?: (contact: Contact) => void;
    onDelete?: (contact: Contact) => void;
    onView?: (contact: Contact) => void;
    onBulkAction?: (contacts: Contact[]) => void;
    pageSize?: number;
    initialPage?: number;
}

export function ContactsTable({
    data,
    isLoading = false,
    isError = false,
    errorMessage = "Failed to load contacts",
    onEdit,
    onDelete,
    onView,
    onBulkAction,
    pageSize = 10,
    initialPage = 1,
}: ContactsTableProps) {
    const [sorting, setSorting] = useState<SortingState>([]);
    const [globalFilter, setGlobalFilter] = useState("");
    const [rowSelection, setRowSelection] = useState<Record<string, boolean>>({});
    const [pagination, setPagination] = useState({
        pageIndex: initialPage - 1,
        pageSize,
    });

    const columns = useMemo(
        () =>
            createContactsColumns({
                onEdit,
                onDelete,
                onView,
            }),
        [onEdit, onDelete, onView]
    );

    const selectedRows = useMemo(() => {
        const selectedIds = Object.keys(rowSelection).filter(
            (id) => rowSelection[id]
        );
        return data.filter((contact) => selectedIds.includes(String(contact.id)));
    }, [data, rowSelection]);

    const table = useReactTable({
        data,
        columns,
        state: {
            sorting,
            globalFilter,
            rowSelection,
            pagination,
        },
        onSortingChange: setSorting,
        onGlobalFilterChange: setGlobalFilter,
        onRowSelectionChange: setRowSelection,
        onPaginationChange: setPagination,
        getCoreRowModel: getCoreRowModel(),
        getSortedRowModel: getSortedRowModel(),
        getFilteredRowModel: getFilteredRowModel(),
        getPaginationRowModel: getPaginationRowModel(),
        getRowId: (row) => String(row.id),
        initialState: {
            pagination: {
                pageIndex: initialPage - 1,
                pageSize,
            },
        },
    });

    const handleSelectAll = useCallback(() => {
        if (table.getIsAllRowsSelected()) {
            table.resetRowSelection();
        } else {
            table.toggleAllRowsSelected(true);
        }
    }, [table]);

    const handleBulkAction = useCallback(() => {
        if (onBulkAction && selectedRows.length > 0) {
            onBulkAction(selectedRows);
        }
    }, [onBulkAction, selectedRows]);

    if (isError) {
        return (
            <div className="rounded-lg border border-red-200 bg-red-50 p-8 text-center dark:border-red-800 dark:bg-red-950">
                <p className="text-red-600 dark:text-red-400">{errorMessage}</p>
            </div>
        );
    }

    const pageCount = table.getPageCount();
    const currentPage = table.getState().pagination.pageIndex + 1;
    const totalRows = table.getFilteredRowModel().rows.length;

    return (
        <div className="space-y-4">
            <div className="flex items-center gap-4">
                <div className="flex-1 max-w-sm">
                    <Input
                        placeholder="Search contacts..."
                        value={globalFilter}
                        onChange={(e) => setGlobalFilter(e.target.value)}
                        className="w-full"
                    />
                </div>
                {selectedRows.length > 0 && onBulkAction && (
                    <Button
                        variant="outline"
                        size="sm"
                        onClick={handleBulkAction}
                    >
                        Action ({selectedRows.length})
                    </Button>
                )}
            </div>

            <div className="rounded-lg border border-border overflow-hidden">
                <table className="w-full">
                    <thead className="bg-muted/50 border-b">
                        {table.getHeaderGroups().map((headerGroup) => (
                            <tr key={headerGroup.id}>
                                {headerGroup.headers.map((header) => (
                                    <th
                                        key={header.id}
                                        className="px-4 py-3 text-left text-sm font-medium text-muted-foreground"
                                        style={{
                                            width: header.getSize() !== 150
                                                ? `${header.getSize()}px`
                                                : "auto",
                                        }}
                                    >
                                        {header.isPlaceholder
                                            ? null
                                            : flexRender(
                                                header.column.columnDef.header,
                                                header.getContext()
                                            )}
                                    </th>
                                ))}
                            </tr>
                        ))}
                    </thead>
                    <tbody>
                        {isLoading ? (
                            <tr>
                                <td
                                    colSpan={columns.length}
                                    className="px-4 py-12 text-center"
                                >
                                    <div className="flex items-center justify-center gap-2">
                                        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                                        <span className="text-muted-foreground">
                                            Loading contacts...
                                        </span>
                                    </div>
                                </td>
                            </tr>
                        ) : totalRows === 0 ? (
                            <tr>
                                <td
                                    colSpan={columns.length}
                                    className="px-4 py-12 text-center text-muted-foreground"
                                >
                                    {globalFilter
                                        ? "No contacts match your search"
                                        : "No contacts found"}
                                </td>
                            </tr>
                        ) : (
                            table.getRowModel().rows.map((row) => (
                                <tr
                                    key={row.id}
                                    className={cn(
                                        "border-b transition-colors hover:bg-muted/50",
                                        row.getIsSelected() && "bg-muted"
                                    )}
                                >
                                    {row.getVisibleCells().map((cell) => (
                                        <td
                                            key={cell.id}
                                            className="px-4 py-3 text-sm"
                                        >
                                            {flexRender(
                                                cell.column.columnDef.cell,
                                                cell.getContext()
                                            )}
                                        </td>
                                    ))}
                                </tr>
                            ))
                        )}
                    </tbody>
                </table>
            </div>

            {totalRows > 0 && (
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2 text-sm text-muted-foreground">
                        <span>
                            Showing {pagination.pageIndex * pagination.pageSize + 1} to{" "}
                            {Math.min(
                                (pagination.pageIndex + 1) * pagination.pageSize,
                                totalRows
                            )}{" "}
                            of {totalRows} contacts
                        </span>
                    </div>
                    <div className="flex items-center gap-1">
                        <Button
                            variant="outline"
                            size="icon"
                            className="h-8 w-8"
                            onClick={() => table.setPageIndex(0)}
                            disabled={!table.getCanPreviousPage()}
                        >
                            <ChevronsLeft className="h-4 w-4" />
                        </Button>
                        <Button
                            variant="outline"
                            size="icon"
                            className="h-8 w-8"
                            onClick={() => table.previousPage()}
                            disabled={!table.getCanPreviousPage()}
                        >
                            <ChevronLeft className="h-4 w-4" />
                        </Button>
                        <span className="text-sm px-2">
                            Page {currentPage} of {pageCount}
                        </span>
                        <Button
                            variant="outline"
                            size="icon"
                            className="h-8 w-8"
                            onClick={() => table.nextPage()}
                            disabled={!table.getCanNextPage()}
                        >
                            <ChevronRight className="h-4 w-4" />
                        </Button>
                        <Button
                            variant="outline"
                            size="icon"
                            className="h-8 w-8"
                            onClick={() => table.setPageIndex(pageCount - 1)}
                            disabled={!table.getCanNextPage()}
                        >
                            <ChevronsRight className="h-4 w-4" />
                        </Button>
                    </div>
                </div>
            )}
        </div>
    );
}