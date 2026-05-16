"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
    listContacts,
    getContact,
    createContact,
    updateContact,
    deleteContact,
    uploadContactsCsv,
    getContactActivities,
    getContactNotes,
    addContactNote,
    deleteContactNote,
    getContactAttributes,
    updateContactAttributes,
    getTags,
    createTag,
    getAttributeDefinitions,
    previewSegmentCount,
    listSegments,
    createSegment,
    updateSegment,
    deleteSegment,
} from "@/lib/services/contacts";
import type {
    Contact,
    ContactCreateRequest,
    ContactsQueryParams,
} from "@/lib/types/contact";

export const CONTACT_QUERY_KEYS = {
    all: ["contacts"] as const,
    list: (params?: ContactsQueryParams) => [...CONTACT_QUERY_KEYS.all, "list", params] as const,
    detail: (id: number) => [...CONTACT_QUERY_KEYS.all, "detail", id] as const,
    activities: (id: number) => [...CONTACT_QUERY_KEYS.all, "activities", id] as const,
    notes: (id: number) => [...CONTACT_QUERY_KEYS.all, "notes", id] as const,
    attributes: (id: number) => [...CONTACT_QUERY_KEYS.all, "attributes", id] as const,
    tags: ["tags"] as const,
    attributeDefinitions: ["attributeDefinitions"] as const,
    segments: ["segments"] as const,
};

export function useContacts(params: ContactsQueryParams = {}) {
    return useQuery({
        queryKey: CONTACT_QUERY_KEYS.list(params),
        queryFn: () => listContacts(params),
    });
}

export function useContact(contactId: number) {
    return useQuery({
        queryKey: CONTACT_QUERY_KEYS.detail(contactId),
        queryFn: () => getContact(contactId),
        enabled: !!contactId,
    });
}

export function useCreateContact() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: (data: ContactCreateRequest) => createContact(data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: CONTACT_QUERY_KEYS.all });
        },
    });
}

export function useUpdateContact() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: ({ id, data }: { id: number; data: Partial<ContactCreateRequest> }) =>
            updateContact(id, data),
        onSuccess: (_, variables) => {
            queryClient.invalidateQueries({ queryKey: CONTACT_QUERY_KEYS.detail(variables.id) });
            queryClient.invalidateQueries({ queryKey: CONTACT_QUERY_KEYS.all });
        },
    });
}

export function useDeleteContact() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: (id: number) => deleteContact(id),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: CONTACT_QUERY_KEYS.all });
        },
    });
}

export function useUploadContactsCsv() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: (file: File) => uploadContactsCsv(file),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: CONTACT_QUERY_KEYS.all });
        },
    });
}

export function useContactActivities(contactId: number) {
    return useQuery({
        queryKey: CONTACT_QUERY_KEYS.activities(contactId),
        queryFn: () => getContactActivities(contactId),
        enabled: !!contactId,
    });
}

export function useContactNotes(contactId: number) {
    return useQuery({
        queryKey: CONTACT_QUERY_KEYS.notes(contactId),
        queryFn: () => getContactNotes(contactId),
        enabled: !!contactId,
    });
}

export function useAddContactNote() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: ({ contactId, body }: { contactId: number; body: string }) =>
            addContactNote(contactId, body),
        onSuccess: (_, variables) => {
            queryClient.invalidateQueries({ queryKey: CONTACT_QUERY_KEYS.notes(variables.contactId) });
        },
    });
}

export function useDeleteContactNote() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: ({ contactId, noteId }: { contactId: number; noteId: number }) =>
            deleteContactNote(contactId, noteId),
        onSuccess: (_, variables) => {
            queryClient.invalidateQueries({ queryKey: CONTACT_QUERY_KEYS.notes(variables.contactId) });
        },
    });
}

export function useContactAttributes(contactId: number) {
    return useQuery({
        queryKey: CONTACT_QUERY_KEYS.attributes(contactId),
        queryFn: () => getContactAttributes(contactId),
        enabled: !!contactId,
    });
}

export function useUpdateContactAttributes() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: ({
            contactId,
            attributes,
        }: {
            contactId: number;
            attributes: Record<string, string | number | boolean | null>;
        }) => updateContactAttributes(contactId, attributes),
        onSuccess: (_, variables) => {
            queryClient.invalidateQueries({
                queryKey: CONTACT_QUERY_KEYS.attributes(variables.contactId),
            });
        },
    });
}

export function useTags() {
    return useQuery({
        queryKey: CONTACT_QUERY_KEYS.tags,
        queryFn: getTags,
    });
}

export function useCreateTag() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: ({ name, color }: { name: string; color?: string }) =>
            createTag(name, color),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: CONTACT_QUERY_KEYS.tags });
        },
    });
}

export function useAttributeDefinitions() {
    return useQuery({
        queryKey: CONTACT_QUERY_KEYS.attributeDefinitions,
        queryFn: getAttributeDefinitions,
    });
}

export function useSegments() {
    return useQuery({
        queryKey: CONTACT_QUERY_KEYS.segments,
        queryFn: listSegments,
    });
}

export function usePreviewSegmentCount() {
    return useMutation({
        mutationFn: (definition: Record<string, unknown>) => previewSegmentCount(definition),
    });
}

export function useCreateSegment() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: ({ name, definition }: { name: string; definition: Record<string, unknown> }) =>
            createSegment(name, definition),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: CONTACT_QUERY_KEYS.segments });
        },
    });
}

export function useUpdateSegment() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: ({ id, name, definition }: { id: number; name: string; definition: Record<string, unknown> }) =>
            updateSegment(id, name, definition),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: CONTACT_QUERY_KEYS.segments });
        },
    });
}

export function useDeleteSegment() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: (id: number) => deleteSegment(id),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: CONTACT_QUERY_KEYS.segments });
        },
    });
}

export function useMaterializeSegment() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: (segmentId: number) => materializeSegment(segmentId),
        onSuccess: (_, segmentId) => {
            queryClient.invalidateQueries({ queryKey: CONTACT_QUERY_KEYS.detail(segmentId) });
            queryClient.invalidateQueries({ queryKey: CONTACT_QUERY_KEYS.segments });
        },
    });
}

// Contact Import Hooks
export const IMPORT_QUERY_KEYS = {
    all: ["contactImports"] as const,
    list: () => [...IMPORT_QUERY_KEYS.all, "list"] as const,
    detail: (id: number) => [...IMPORT_QUERY_KEYS.all, "detail", id] as const,
    errors: (id: number) => [...IMPORT_QUERY_KEYS.all, "errors", id] as const,
};

export function useContactImportJobs() {
    return useQuery({
        queryKey: IMPORT_QUERY_KEYS.list(),
        queryFn: listContactImportJobs,
        refetchInterval: (query) => {
            const job = query.state.data?.find((j) => j.status === "queued" || j.status === "processing");
            return job ? 2000 : false;
        },
    });
}

export function useContactImportJob(jobId: number) {
    return useQuery({
        queryKey: IMPORT_QUERY_KEYS.detail(jobId),
        queryFn: () => getContactImportJob(jobId),
        enabled: !!jobId,
        refetchInterval: (query) => {
            const job = query.state.data;
            if (job && (job.status === "queued" || job.status === "processing")) {
                return 2000;
            }
            return false;
        },
    });
}

export function useContactImportErrors(jobId: number) {
    return useQuery({
        queryKey: IMPORT_QUERY_KEYS.errors(jobId),
        queryFn: () => getContactImportErrors(jobId),
        enabled: !!jobId,
    });
}

export function useCreateContactImportJob() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: (file: File) => createContactImportJob(file),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: IMPORT_QUERY_KEYS.list() });
        },
    });
}