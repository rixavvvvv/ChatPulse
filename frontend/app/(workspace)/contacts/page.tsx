"use client";

import { useState, useCallback, useMemo } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Plus, Upload, AlertCircle, X, Filter, Users, History, Database, Layers, RefreshCw } from "lucide-react";
import toast from "react-hot-toast";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/states";
import { ContactsTable, ContactDetailsDrawer, FilterBuilder, FilterChips, SegmentBuilder, SegmentList, SegmentMaterializationPanel, CsvImportModal, ImportJobsPanel } from "@/components/contacts";
import {
    useContacts,
    useCreateContact,
    useDeleteContact,
    useTags,
    useAttributeDefinitions,
    useSegments,
    usePreviewSegmentCount,
    useCreateSegment,
    useDeleteSegment,
    useMaterializeSegment,
} from "@/hooks/use-contacts";
import type { Contact, ContactCreateRequest, FilterNode, SegmentNode } from "@/lib/types/contact";

export default function ContactsPage() {
    const [showAddForm, setShowAddForm] = useState(false);
    const [showCsvModal, setShowCsvModal] = useState(false);
    const [showImportHistory, setShowImportHistory] = useState(false);
    const [showFilters, setShowFilters] = useState(false);
    const [showSegmentBuilder, setShowSegmentBuilder] = useState(false);
    const [showMaterialization, setShowMaterialization] = useState(false);
    const [name, setName] = useState("");
    const [phone, setPhone] = useState("");
    const [tags, setTags] = useState("");
    const [selectedContacts, setSelectedContacts] = useState<Contact[]>([]);
    const [selectedContactId, setSelectedContactId] = useState<number | null>(null);
    const [isDrawerOpen, setIsDrawerOpen] = useState(false);
    const [filterDefinition, setFilterDefinition] = useState<FilterNode | undefined>();
    const [editingSegmentId, setEditingSegmentId] = useState<number | null>(null);
    const [segmentDefinition, setSegmentDefinition] = useState<SegmentNode | undefined>();

    const { data: contacts = [], isLoading, isError, error, refetch } = useContacts();
    const { data: availableTags = [] } = useTags();
    const { data: availableAttributes = [] } = useAttributeDefinitions();
    const { data: savedFilters = [] } = useSegments();
    const previewMutation = usePreviewSegmentCount();
    const createSegmentMutation = useCreateSegment();
    const deleteSegmentMutation = useDeleteSegment();
    const materializeMutation = useMaterializeSegment();

    const [materializingSegments, setMaterializingSegments] = useState<Set<number>>(new Set());

    const createContactMutation = useCreateContact();
    const deleteContactMutation = useDeleteContact();

    const handleMaterializeSegment = useCallback(async (segmentId: number) => {
        setMaterializingSegments((prev) => new Set(prev).add(segmentId));
        try {
            await materializeMutation.mutateAsync(segmentId);
            toast.success("Segment materialization started");
        } catch (err) {
            toast.error(err instanceof Error ? err.message : "Failed to start materialization");
        } finally {
            setMaterializingSegments((prev) => {
                const next = new Set(prev);
                next.delete(segmentId);
                return next;
            });
        }
    }, [materializeMutation]);

    const handleMaterializeAll = useCallback(async () => {
        const unmaterialized = savedFilters.filter((f) => !f.last_materialized_at && !materializingSegments.has(f.id));
        for (const segment of unmaterialized) {
            setMaterializingSegments((prev) => new Set(prev).add(segment.id));
        }
        try {
            for (const segment of unmaterialized) {
                await materializeMutation.mutateAsync(segment.id);
            }
            toast.success(`Materialization started for ${unmaterialized.length} segments`);
        } catch (err) {
            toast.error(err instanceof Error ? err.message : "Failed to start materialization");
        } finally {
            setMaterializingSegments(new Set());
        }
    }, [savedFilters, materializeMutation, materializingSegments]);

    const isSegmentMaterializing = useCallback((segmentId: number) => {
        return materializingSegments.has(segmentId);
    }, [materializingSegments]);

    const handlePreviewFilter = useCallback(async (definition: FilterNode): Promise<number> => {
        try {
            const count = await previewMutation.mutateAsync(definition as unknown as Record<string, unknown>);
            return count;
        } catch (err) {
            toast.error(err instanceof Error ? err.message : "Failed to preview filter");
            return 0;
        }
    }, [previewMutation]);

    const handleSaveFilter = useCallback(async (name: string, definition: FilterNode) => {
        try {
            await createSegmentMutation.mutateAsync({
                name,
                definition: definition as unknown as Record<string, unknown>,
            });
            toast.success(`Filter "${name}" saved`);
        } catch (err) {
            toast.error(err instanceof Error ? err.message : "Failed to save filter");
        }
    }, [createSegmentMutation]);

    const handleLoadFilter = useCallback((definition: FilterNode) => {
        setFilterDefinition(definition);
    }, []);

    const handleClearFilter = useCallback(() => {
        setFilterDefinition(undefined);
    }, []);

    const handleSegmentChange = useCallback((definition: SegmentNode) => {
        setSegmentDefinition(definition);
    }, []);

    const handlePreviewSegment = useCallback(async (definition: SegmentNode): Promise<number> => {
        try {
            const count = await previewMutation.mutateAsync(definition as unknown as Record<string, unknown>);
            return count;
        } catch (err) {
            toast.error(err instanceof Error ? err.message : "Failed to preview segment");
            return 0;
        }
    }, [previewMutation]);

    const handleSaveSegment = useCallback(async (segmentName: string, definition: SegmentNode) => {
        try {
            await createSegmentMutation.mutateAsync({
                name: segmentName,
                definition: definition as unknown as Record<string, unknown>,
            });
            toast.success(`Segment "${segmentName}" created`);
            setShowSegmentBuilder(false);
            setSegmentDefinition(undefined);
        } catch (err) {
            toast.error(err instanceof Error ? err.message : "Failed to save segment");
        }
    }, [createSegmentMutation]);

    const handleEditSegment = useCallback((segmentId: number) => {
        const segment = savedFilters.find(s => s.id === segmentId);
        if (segment) {
            setEditingSegmentId(segmentId);
            setSegmentDefinition(segment.definition as unknown as SegmentNode);
            setShowSegmentBuilder(true);
        }
    }, [savedFilters]);

    const handleDuplicateSegment = useCallback(async (segmentId: number) => {
        const segment = savedFilters.find(s => s.id === segmentId);
        if (segment) {
            try {
                await createSegmentMutation.mutateAsync({
                    name: `${segment.name} (Copy)`,
                    definition: segment.definition as unknown as Record<string, unknown>,
                });
                toast.success(`Segment duplicated`);
            } catch (err) {
                toast.error(err instanceof Error ? err.message : "Failed to duplicate segment");
            }
        }
    }, [savedFilters, createSegmentMutation]);

    const handleDeleteSegment = useCallback(async (segmentId: number) => {
        if (!confirm("Are you sure you want to delete this segment?")) return;
        try {
            await deleteSegmentMutation.mutateAsync(segmentId);
            toast.success("Segment deleted");
            if (editingSegmentId === segmentId) {
                setEditingSegmentId(null);
                setSegmentDefinition(undefined);
                setShowSegmentBuilder(false);
            }
        } catch (err) {
            toast.error(err instanceof Error ? err.message : "Failed to delete segment");
        }
    }, [deleteSegmentMutation, editingSegmentId]);

    const handleAddContact = useCallback(async (e: React.FormEvent) => {
        e.preventDefault();

        if (!name.trim() || !phone.trim()) {
            toast.error("Name and phone are required");
            return;
        }

        try {
            const contactData: ContactCreateRequest = {
                name: name.trim(),
                phone: phone.trim(),
                tags: tags.trim() ? tags.split(",").map((t) => t.trim()).filter(Boolean) : [],
            };

            await createContactMutation.mutateAsync(contactData);
            toast.success("Contact added successfully");
            setName("");
            setPhone("");
            setTags("");
            setShowAddForm(false);
        } catch (err) {
            toast.error(err instanceof Error ? err.message : "Failed to add contact");
        }
    }, [name, phone, tags, createContactMutation]);

    const handleEditContact = useCallback((contact: Contact) => {
        setSelectedContactId(contact.id);
        setIsDrawerOpen(true);
    }, []);

    const handleDeleteContact = useCallback(async (contact: Contact) => {
        if (!confirm(`Are you sure you want to delete ${contact.name}?`)) {
            return;
        }

        try {
            await deleteContactMutation.mutateAsync(contact.id);
            toast.success("Contact deleted");
        } catch (err) {
            toast.error(err instanceof Error ? err.message : "Failed to delete contact");
        }
    }, [deleteContactMutation]);

    const handleViewContact = useCallback((contact: Contact) => {
        setSelectedContactId(contact.id);
        setIsDrawerOpen(true);
    }, []);

    const handleBulkAction = useCallback((contacts: Contact[]) => {
        setSelectedContacts(contacts);
        toast(`${contacts.length} contacts selected`, { icon: "ℹ️" });
    }, []);

    const handleCloseDrawer = useCallback(() => {
        setIsDrawerOpen(false);
    }, []);

    if (isError) {
        return (
            <div className="space-y-6">
                <section className="flex flex-col justify-between gap-4 rounded-3xl border border-border/70 bg-white/80 p-6 shadow-soft sm:flex-row sm:items-center">
                    <div>
                        <p className="text-xs font-semibold uppercase tracking-[0.22em] text-sky-700">Contacts</p>
                        <h2 className="mt-2 font-[var(--font-space-grotesk)] text-3xl font-semibold">Audience Directory</h2>
                        <p className="mt-2 text-sm text-muted-foreground">Import and segment your recipients before launching campaigns.</p>
                    </div>
                </section>

                <Card>
                    <CardContent className="pt-6">
                        <EmptyState
                            title="Failed to load contacts"
                            description={error instanceof Error ? error.message : "Something went wrong"}
                            icon={AlertCircle}
                            action={
                                <Button onClick={() => refetch()}>
                                    Try Again
                                </Button>
                            }
                        />
                    </CardContent>
                </Card>
            </div>
        );
    }

    return (
        <div className="space-y-6">
            <section className="flex flex-col justify-between gap-4 rounded-3xl border border-border/70 bg-white/80 p-6 shadow-soft sm:flex-row sm:items-center">
                <div>
                    <p className="text-xs font-semibold uppercase tracking-[0.22em] text-sky-700">Contacts</p>
                    <h2 className="mt-2 font-[var(--font-space-grotesk)] text-3xl font-semibold">Audience Directory</h2>
                    <p className="mt-2 text-sm text-muted-foreground">
                        Import and segment your recipients before launching campaigns.
                        {contacts.length > 0 && (
                            <span className="ml-2">
                                <Badge variant="secondary">{contacts.length} contacts</Badge>
                            </span>
                        )}
                    </p>
                </div>
                <div className="flex gap-2">
                    <Button
                        variant={showSegmentBuilder ? "default" : "outline"}
                        onClick={() => {
                            setShowSegmentBuilder(!showSegmentBuilder);
                            if (!showSegmentBuilder) {
                                setShowFilters(false);
                            }
                        }}
                    >
                        <Database className="mr-2 h-4 w-4" />
                        Segments
                    </Button>
                    <Button
                        variant={showFilters ? "default" : "outline"}
                        onClick={() => {
                            setShowFilters(!showFilters);
                            if (!showFilters) {
                                setShowSegmentBuilder(false);
                            }
                        }}
                    >
                        <Filter className="mr-2 h-4 w-4" />
                        Filter
                    </Button>
                    <Button
                        variant={showMaterialization ? "default" : "outline"}
                        onClick={() => {
                            setShowMaterialization(!showMaterialization);
                            if (!showMaterialization) {
                                setShowSegmentBuilder(false);
                                setShowFilters(false);
                            }
                        }}
                    >
                        <RefreshCw className="mr-2 h-4 w-4" />
                        Materialize
                    </Button>
                    <Button
                        variant="outline"
                        onClick={() => setShowImportHistory(true)}
                    >
                        <History className="mr-2 h-4 w-4" />
                        Import History
                    </Button>
                    <Button
                        variant="outline"
                        onClick={() => setShowCsvModal(true)}
                    >
                        <Upload className="mr-2 h-4 w-4" />
                        Import CSV
                    </Button>
                    <Button onClick={() => setShowAddForm(!showAddForm)}>
                        <Plus className="mr-2 h-4 w-4" />
                        Add Contact
                    </Button>
                </div>
            </section>

            {showSegmentBuilder && (
                <div className="grid gap-6 lg:grid-cols-3">
                    <div className="lg:col-span-2">
                        <Card>
                            <CardContent className="pt-4">
                                <SegmentBuilder
                                    definition={segmentDefinition}
                                    onChange={handleSegmentChange}
                                    onPreview={handlePreviewSegment}
                                    onSave={handleSaveSegment}
                                    existingSegments={savedFilters.map((f) => ({
                                        id: f.id,
                                        name: f.name,
                                        definition: f.definition as unknown as SegmentNode,
                                    }))}
                                    editingSegmentId={editingSegmentId}
                                    availableTags={availableTags}
                                    availableAttributes={availableAttributes.map((attr) => ({
                                        id: attr.id,
                                        key: attr.key,
                                        label: attr.label,
                                        type: attr.type,
                                    }))}
                                />
                            </CardContent>
                        </Card>
                    </div>
                    <div>
                        <Card>
                            <CardHeader className="pb-3">
                                <CardTitle className="text-sm font-medium flex items-center gap-2">
                                    <Layers className="h-4 w-4" />
                                    Saved Segments
                                </CardTitle>
                            </CardHeader>
                            <CardContent>
                                <SegmentList
                                    segments={savedFilters.map((f) => ({
                                        id: f.id,
                                        name: f.name,
                                        approx_size: (f as unknown as { approx_size?: number }).approx_size || 0,
                                        status: (f as unknown as { status?: string }).status || "active",
                                        created_at: f.created_at,
                                    }))}
                                    onEdit={handleEditSegment}
                                    onDuplicate={handleDuplicateSegment}
                                    onDelete={handleDeleteSegment}
                                />
                            </CardContent>
                        </Card>
                    </div>
                </div>
            )}

            {showFilters && !showSegmentBuilder && (
                <Card>
                    <CardContent className="pt-4">
                        <FilterBuilder
                            definition={filterDefinition}
                            onChange={setFilterDefinition}
                            onPreview={handlePreviewFilter}
                            availableTags={availableTags}
                            availableAttributes={availableAttributes.map((attr) => ({
                                id: attr.id,
                                key: attr.key,
                                label: attr.label,
                                type: attr.type,
                            }))}
                            savedFilters={savedFilters.map((f) => ({
                                id: f.id,
                                name: f.name,
                                definition: f.definition as unknown as FilterNode,
                                created_at: f.created_at,
                            }))}
                            onSaveFilter={handleSaveFilter}
                            onLoadFilter={handleLoadFilter}
                        />
                    </CardContent>
                </Card>
            )}

            {showMaterialization && (
                <Card>
                    <CardHeader className="pb-3">
                        <CardTitle className="text-lg flex items-center gap-2">
                            <RefreshCw className="h-5 w-5" />
                            Segment Materialization
                        </CardTitle>
                        <CardDescription>
                            Materialize segments to compute and cache membership for faster queries
                        </CardDescription>
                    </CardHeader>
                    <CardContent>
                        <SegmentMaterializationPanel
                            segments={savedFilters.map((f) => ({
                                id: f.id,
                                name: f.name,
                                approx_size: (f as unknown as { approx_size?: number }).approx_size || 0,
                                last_materialized_at: (f as unknown as { last_materialized_at?: string }).last_materialized_at || null,
                                status: (f as unknown as { status?: string }).status || "inactive",
                                materializing: materializingSegments.has(f.id),
                                error_message: (f as unknown as { error_message?: string }).error_message || null,
                            }))}
                            onMaterialize={handleMaterializeSegment}
                            isMaterializing={isSegmentMaterializing}
                            onRefreshAll={handleMaterializeAll}
                            isRefreshingAll={materializingSegments.size > 0}
                        />
                    </CardContent>
                </Card>
            )}

            {filterDefinition && (
                <FilterChips
                    definition={filterDefinition}
                    onClear={handleClearFilter}
                    availableTags={availableTags}
                    availableAttributes={availableAttributes.map((attr) => ({
                        id: attr.id,
                        key: attr.key,
                        label: attr.label,
                        type: attr.type,
                    }))}
                />
            )}

            {showAddForm && (
                <Card>
                    <CardHeader>
                        <CardTitle className="flex items-center gap-2 text-xl">
                            <Plus className="h-4 w-4" />
                            Add Contact
                        </CardTitle>
                        <CardDescription>Add a single recipient to the active workspace.</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <form className="space-y-3" onSubmit={handleAddContact}>
                            <Input
                                placeholder="Name"
                                value={name}
                                onChange={(e) => setName(e.target.value)}
                                required
                            />
                            <Input
                                placeholder="Phone (+14155550101)"
                                value={phone}
                                onChange={(e) => setPhone(e.target.value)}
                                required
                            />
                            <Input
                                placeholder="Tags (comma separated)"
                                value={tags}
                                onChange={(e) => setTags(e.target.value)}
                            />
                            <div className="flex gap-2">
                                <Button
                                    type="submit"
                                    disabled={createContactMutation.isPending}
                                >
                                    {createContactMutation.isPending ? "Adding..." : "Add Contact"}
                                </Button>
                                <Button
                                    type="button"
                                    variant="outline"
                                    onClick={() => setShowAddForm(false)}
                                >
                                    Cancel
                                </Button>
                            </div>
                        </form>
                    </CardContent>
                </Card>
            )}

            {selectedContacts.length > 0 && (
                <Card className="bg-muted/50">
                    <CardContent className="py-3 flex items-center justify-between">
                        <span className="text-sm">
                            {selectedContacts.length} contact{selectedContacts.length > 1 ? "s" : ""} selected
                        </span>
                        <div className="flex gap-2">
                            <Button size="sm" variant="outline">
                                Add Tags
                            </Button>
                            <Button size="sm" variant="outline">
                                Delete
                            </Button>
                            <Button
                                size="sm"
                                variant="ghost"
                                onClick={() => setSelectedContacts([])}
                            >
                                <X className="h-4 w-4" />
                            </Button>
                        </div>
                    </CardContent>
                </Card>
            )}

            <ContactsTable
                data={contacts}
                isLoading={isLoading}
                isError={isError}
                errorMessage={error instanceof Error ? error.message : "Failed to load contacts"}
                onEdit={handleEditContact}
                onDelete={handleDeleteContact}
                onView={handleViewContact}
                onBulkAction={handleBulkAction}
                pageSize={10}
            />

            <ContactDetailsDrawer
                contactId={selectedContactId}
                isOpen={isDrawerOpen}
                onClose={handleCloseDrawer}
            />

            <CsvImportModal
                isOpen={showCsvModal}
                onClose={() => setShowCsvModal(false)}
                onSuccess={() => {
                    refetch();
                    setShowImportHistory(true);
                }}
            />

            <ImportJobsPanel
                isOpen={showImportHistory}
                onClose={() => setShowImportHistory(false)}
            />
        </div>
    );
}