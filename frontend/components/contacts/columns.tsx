"use client";

import { ColumnDef } from "@tanstack/react-table";
import { ArrowUpDown, MoreHorizontal, Mail, Phone, Calendar } from "lucide-react";
import { format, parseISO, isValid } from "date-fns";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Badge } from "@/components/ui/badge";
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import type { Contact } from "@/lib/types/contact";

function formatDate(dateString: string | undefined): string {
    if (!dateString) return "—";
    try {
        const date = parseISO(dateString);
        if (!isValid(date)) return "—";
        return format(date, "MMM d, yyyy");
    } catch {
        return "—";
    }
}

function formatRelativeTime(dateString: string | undefined): string {
    if (!dateString) return "No activity";
    try {
        const date = parseISO(dateString);
        if (!isValid(date)) return "No activity";

        const now = new Date();
        const diffInMs = now.getTime() - date.getTime();
        const diffInDays = Math.floor(diffInMs / (1000 * 60 * 60 * 24));

        if (diffInDays === 0) return "Today";
        if (diffInDays === 1) return "Yesterday";
        if (diffInDays < 7) return `${diffInDays} days ago`;
        if (diffInDays < 30) return `${Math.floor(diffInDays / 7)} weeks ago`;
        if (diffInDays < 365) return `${Math.floor(diffInDays / 30)} months ago`;
        return `${Math.floor(diffInDays / 365)} years ago`;
    } catch {
        return "No activity";
    }
}

function StatusBadge({ status }: { status?: string }) {
    if (!status) {
        return (
            <Badge variant="outline" className="bg-gray-50 text-gray-600">
                Unknown
            </Badge>
        );
    }

    const variants: Record<string, "default" | "success" | "warning" | "error"> = {
        active: "success",
        inactive: "warning",
    };

    return (
        <Badge variant={variants[status] || "outline"}>
            {status.charAt(0).toUpperCase() + status.slice(1)}
        </Badge>
    );
}

function TagsList({ tags }: { tags: string[] }) {
    if (!tags || tags.length === 0) {
        return <span className="text-muted-foreground text-sm">No tags</span>;
    }

    return (
        <div className="flex flex-wrap gap-1">
            {tags.slice(0, 3).map((tag) => (
                <Badge key={tag} variant="outline" className="text-xs">
                    {tag}
                </Badge>
            ))}
            {tags.length > 3 && (
                <Badge variant="outline" className="text-xs">
                    +{tags.length - 3}
                </Badge>
            )}
        </div>
    );
}

interface ContactsColumnsProps {
    onEdit?: (contact: Contact) => void;
    onDelete?: (contact: Contact) => void;
    onView?: (contact: Contact) => void;
}

export function createContactsColumns({
    onEdit,
    onDelete,
    onView,
}: ContactsColumnsProps = {}): ColumnDef<Contact>[] {
    return [
        {
            id: "select",
            header: ({ table }) => (
                <Checkbox
                    checked={table.getIsAllRowsSelected()}
                    onChange={table.getToggleAllRowsSelectedHandler()}
                    aria-label="Select all"
                />
            ),
            cell: ({ row }) => (
                <Checkbox
                    checked={row.getIsSelected()}
                    onChange={row.getToggleSelectedHandler()}
                    aria-label="Select row"
                />
            ),
            enableSorting: false,
            enableHiding: false,
            size: 40,
        },
        {
            accessorKey: "name",
            header: ({ column }) => {
                return (
                    <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}
                        className="-ml-4 h-8"
                    >
                        Name
                        <ArrowUpDown className="ml-2 h-4 w-4" />
                    </Button>
                );
            },
            cell: ({ row }) => {
                const name = row.getValue("name") as string;
                return (
                    <div className="flex flex-col">
                        <span className="font-medium">{name || "—"}</span>
                    </div>
                );
            },
            size: 200,
        },
        {
            accessorKey: "phone",
            header: ({ column }) => {
                return (
                    <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}
                        className="-ml-4 h-8"
                    >
                        Phone
                        <ArrowUpDown className="ml-2 h-4 w-4" />
                    </Button>
                );
            },
            cell: ({ row }) => {
                const phone = row.getValue("phone") as string;
                return (
                    <div className="flex items-center gap-2">
                        <Phone className="h-3 w-3 text-muted-foreground" />
                        <span className="font-mono text-sm">{phone}</span>
                    </div>
                );
            },
            size: 150,
        },
        {
            accessorKey: "email",
            header: "Email",
            cell: ({ row }) => {
                const email = row.original as unknown as { email?: string };
                return (
                    <div className="flex items-center gap-2">
                        {email?.email ? (
                            <>
                                <Mail className="h-3 w-3 text-muted-foreground" />
                                <span className="text-sm">{email.email}</span>
                            </>
                        ) : (
                            <span className="text-muted-foreground text-sm">—</span>
                        )}
                    </div>
                );
            },
            size: 200,
        },
        {
            accessorKey: "tags",
            header: "Tags",
            cell: ({ row }) => {
                const tags = row.getValue("tags") as string[];
                return <TagsList tags={tags} />;
            },
            size: 180,
            filterFn: (row, id, value) => {
                const tags = row.getValue(id) as string[];
                return value.some((v: string) => tags.includes(v));
            },
        },
        {
            accessorKey: "status",
            header: "Status",
            cell: ({ row }) => {
                const status = row.getValue("status") as string | undefined;
                return <StatusBadge status={status} />;
            },
            size: 100,
            filterFn: (row, id, value) => {
                const status = row.getValue(id) as string | undefined;
                return value.includes(status || "unknown");
            },
        },
        {
            accessorKey: "last_activity_at",
            header: ({ column }) => {
                return (
                    <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}
                        className="-ml-4 h-8"
                    >
                        Last Activity
                        <ArrowUpDown className="ml-2 h-4 w-4" />
                    </Button>
                );
            },
            cell: ({ row }) => {
                const lastActivity = row.getValue("last_activity_at") as string | undefined;
                return (
                    <div className="flex items-center gap-2">
                        <Calendar className="h-3 w-3 text-muted-foreground" />
                        <span className="text-sm">{formatRelativeTime(lastActivity)}</span>
                    </div>
                );
            },
            size: 150,
        },
        {
            accessorKey: "created_at",
            header: ({ column }) => {
                return (
                    <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}
                        className="-ml-4 h-8"
                    >
                        Created
                        <ArrowUpDown className="ml-2 h-4 w-4" />
                    </Button>
                );
            },
            cell: ({ row }) => {
                const createdAt = row.getValue("created_at") as string;
                return (
                    <span className="text-sm text-muted-foreground">
                        {formatDate(createdAt)}
                    </span>
                );
            },
            size: 120,
        },
        {
            id: "actions",
            cell: ({ row }) => {
                const contact = row.original;

                return (
                    <div className="flex justify-end">
                        <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                                <Button variant="ghost" className="h-8 w-8 p-0">
                                    <span className="sr-only">Open menu</span>
                                    <MoreHorizontal className="h-4 w-4" />
                                </Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end">
                                {onView && (
                                    <DropdownMenuItem onClick={() => onView(contact)}>
                                        View details
                                    </DropdownMenuItem>
                                )}
                                {onEdit && (
                                    <DropdownMenuItem onClick={() => onEdit(contact)}>
                                        Edit contact
                                    </DropdownMenuItem>
                                )}
                                <DropdownMenuSeparator />
                                {onDelete && (
                                    <DropdownMenuItem
                                        onClick={() => onDelete(contact)}
                                        className="text-red-600"
                                    >
                                        Delete
                                    </DropdownMenuItem>
                                )}
                            </DropdownMenuContent>
                        </DropdownMenu>
                    </div>
                );
            },
            size: 50,
        },
    ];
}

export const defaultContactsColumns = createContactsColumns({});