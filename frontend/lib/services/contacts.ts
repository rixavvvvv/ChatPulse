import { apiRequest, getApiUrl } from "@/lib/api";
import { getSession } from "@/lib/session";
import type {
    Contact,
    ContactCreateRequest,
    ContactUploadResponse,
    ContactActivity,
    ContactNote,
    ContactAttribute,
    ContactsQueryParams,
} from "@/lib/types/contact";

const BASE_URL = "/contacts";

async function getAuthHeaders(): Promise<string> {
    const session = getSession();
    if (!session) {
        throw new Error("Authentication required");
    }
    return session.access_token;
}

export async function listContacts(
    params: ContactsQueryParams = {}
): Promise<Contact[]> {
    const token = await getAuthHeaders();

    const queryParams = new URLSearchParams();
    if (params.page) queryParams.set("page", params.page.toString());
    if (params.page_size) queryParams.set("page_size", params.page_size.toString());
    if (params.search) queryParams.set("search", params.search);
    if (params.sort_by) queryParams.set("sort_by", params.sort_by);
    if (params.sort_dir) queryParams.set("sort_dir", params.sort_dir);
    if (params.tags?.length) queryParams.set("tags", params.tags.join(","));
    if (params.status) queryParams.set("status", params.status);

    const queryString = queryParams.toString();
    const url = queryString ? `${BASE_URL}?${queryString}` : BASE_URL;

    return apiRequest<Contact[]>(url, {}, token);
}

export async function getContact(contactId: number): Promise<Contact> {
    const token = await getAuthHeaders();
    return apiRequest<Contact>(`${BASE_URL}/${contactId}`, {}, token);
}

export async function createContact(
    data: ContactCreateRequest
): Promise<Contact> {
    const token = await getAuthHeaders();
    return apiRequest<Contact>(
        BASE_URL,
        {
            method: "POST",
            body: JSON.stringify(data),
        },
        token
    );
}

export async function updateContact(
    contactId: number,
    data: Partial<ContactCreateRequest>
): Promise<Contact> {
    const token = await getAuthHeaders();
    return apiRequest<Contact>(
        `${BASE_URL}/${contactId}`,
        {
            method: "PATCH",
            body: JSON.stringify(data),
        },
        token
    );
}

export async function deleteContact(contactId: number): Promise<void> {
    const token = await getAuthHeaders();
    await apiRequest<void>(
        `${BASE_URL}/${contactId}`,
        { method: "DELETE" },
        token
    );
}

export async function uploadContactsCsv(
    file: File
): Promise<ContactUploadResponse> {
    const token = await getAuthHeaders();
    const formData = new FormData();
    formData.append("file", file);

    const response = await fetch(getApiUrl("/contacts/upload-csv"), {
        method: "POST",
        headers: {
            Authorization: `Bearer ${token}`,
        },
        body: formData,
    });

    if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: "Upload failed" }));
        throw new Error(error.detail || "Failed to upload CSV");
    }

    return response.json();
}

export async function getContactActivities(
    contactId: number
): Promise<ContactActivity[]> {
    const token = await getAuthHeaders();
    return apiRequest<ContactActivity[]>(
        `${BASE_URL}/${contactId}/activities`,
        {},
        token
    );
}

export async function getContactNotes(contactId: number): Promise<ContactNote[]> {
    const token = await getAuthHeaders();
    return apiRequest<ContactNote[]>(
        `${BASE_URL}/${contactId}/notes`,
        {},
        token
    );
}

export async function addContactNote(
    contactId: number,
    body: string
): Promise<ContactNote> {
    const token = await getAuthHeaders();
    return apiRequest<ContactNote>(
        `${BASE_URL}/${contactId}/notes`,
        {
            method: "POST",
            body: JSON.stringify({ body }),
        },
        token
    );
}

export async function deleteContactNote(
    contactId: number,
    noteId: number
): Promise<void> {
    const token = await getAuthHeaders();
    await apiRequest<void>(
        `${BASE_URL}/${contactId}/notes/${noteId}`,
        { method: "DELETE" },
        token
    );
}

export async function getContactAttributes(
    contactId: number
): Promise<ContactAttribute[]> {
    const token = await getAuthHeaders();
    return apiRequest<ContactAttribute[]>(
        `${BASE_URL}/${contactId}/attributes`,
        {},
        token
    );
}

export async function updateContactAttributes(
    contactId: number,
    attributes: Record<string, string | number | boolean | null>
): Promise<ContactAttribute[]> {
    const token = await getAuthHeaders();
    return apiRequest<ContactAttribute[]>(
        `${BASE_URL}/${contactId}/attributes`,
        {
            method: "PUT",
            body: JSON.stringify(attributes),
        },
        token
    );
}

export async function getTags(): Promise<{ id: number; name: string; color: string }[]> {
    const token = await getAuthHeaders();
    return apiRequest<{ id: number; name: string; color: string }[]>(
        "/tags",
        {},
        token
    );
}

export async function createTag(name: string, color: string = "#3b82f6"): Promise<{ id: number; name: string; color: string }> {
    const token = await getAuthHeaders();
    return apiRequest<{ id: number; name: string; color: string }>(
        "/tags",
        {
            method: "POST",
            body: JSON.stringify({ name, color }),
        },
        token
    );
}

export async function getAttributeDefinitions(): Promise<{
    id: number;
    key: string;
    label: string;
    type: string;
    is_indexed: boolean;
}[]> {
    const token = await getAuthHeaders();
    return apiRequest<{
        id: number;
        key: string;
        label: string;
        type: string;
        is_indexed: boolean;
    }[]>("/attributes/definitions", {}, token);
}

export async function previewSegmentCount(definition: Record<string, unknown>): Promise<number> {
    const token = await getAuthHeaders();
    const response = await apiRequest<{ estimated_count: number }>(
        "/segments/preview",
        {
            method: "POST",
            body: JSON.stringify({ definition }),
        },
        token
    );
    return response.estimated_count;
}

export async function listSegments(): Promise<{
    id: number;
    name: string;
    status: string;
    definition: Record<string, unknown>;
    approx_size: number;
    last_materialized_at: string | null;
    created_at: string;
    updated_at: string;
}[]> {
    const token = await getAuthHeaders();
    return apiRequest<{
        id: number;
        name: string;
        status: string;
        definition: Record<string, unknown>;
        approx_size: number;
        last_materialized_at: string | null;
        created_at: string;
        updated_at: string;
    }[]>("/segments", {}, token);
}

export async function createSegment(
    name: string,
    definition: Record<string, unknown>
): Promise<{
    id: number;
    name: string;
    status: string;
    definition: Record<string, unknown>;
    approx_size: number;
}> {
    const token = await getAuthHeaders();
    return apiRequest<{
        id: number;
        name: string;
        status: string;
        definition: Record<string, unknown>;
        approx_size: number;
    }>(
        "/segments",
        {
            method: "POST",
            body: JSON.stringify({ name, definition }),
        },
        token
    );
}

export async function deleteSegment(segmentId: number): Promise<void> {
    const token = await getAuthHeaders();
    await apiRequest<void>(
        `/segments/${segmentId}`,
        { method: "DELETE" },
        token
    );
}

// Segment Materialization Functions
export interface SegmentMaterializationResponse {
    segment_id: number;
    celery_task_id: string | null;
}

export async function materializeSegment(
    segmentId: number
): Promise<SegmentMaterializationResponse> {
    const token = await getAuthHeaders();
    return apiRequest<SegmentMaterializationResponse>(
        `/segments/${segmentId}/materialize`,
        { method: "POST" },
        token
    );
}

export interface SegmentWithMaterialization {
    id: number;
    name: string;
    status: string;
    definition: Record<string, unknown>;
    approx_size: number;
    last_materialized_at: string | null;
    created_at: string;
    updated_at: string;
    materializing?: boolean;
    error_message?: string | null;
}

export function getSegmentStatusInfo(segment: SegmentWithMaterialization): {
    status: "idle" | "materializing" | "ready" | "error";
    label: string;
    color: string;
} {
    if (segment.materializing) {
        return { status: "materializing", label: "Materializing...", color: "blue" };
    }
    if (segment.status === "active" || segment.approx_size > 0) {
        return { status: "ready", label: "Ready", color: "green" };
    }
    if (segment.status === "failed" || segment.error_message) {
        return { status: "error", label: "Error", color: "red" };
    }
    return { status: "idle", label: "Not Materialized", color: "gray" };
}

// Contact Import Functions
export interface ImportJobResponse {
    id: number;
    status: string;
    total_rows: number;
    processed_rows: number;
    inserted_rows: number;
    skipped_rows: number;
    failed_rows: number;
    error_message: string | null;
    created_at: string;
    completed_at: string | null;
}

export interface ImportErrorsResponse {
    job_id: number;
    errors: { row_number: number; error: string; raw: Record<string, string> }[];
}

export async function createContactImportJob(
    file: File
): Promise<{ job_id: number; celery_task_id: string | null }> {
    const token = await getAuthHeaders();
    const formData = new FormData();
    formData.append("file", file);

    const response = await fetch(getApiUrl("/contacts/imports"), {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
    });

    if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: "Import failed" }));
        throw new Error(error.detail || "Failed to create import job");
    }

    return response.json();
}

export async function getContactImportJob(jobId: number): Promise<ImportJobResponse> {
    const token = await getAuthHeaders();
    return apiRequest<ImportJobResponse>(`/contacts/imports/${jobId}`, {}, token);
}

export async function listContactImportJobs(limit = 20): Promise<ImportJobResponse[]> {
    const token = await getAuthHeaders();
    return apiRequest<ImportJobResponse[]>(`/contacts/imports`, {}, token);
}

export async function getContactImportErrors(jobId: number): Promise<ImportErrorsResponse> {
    const token = await getAuthHeaders();
    return apiRequest<ImportErrorsResponse>(`/contacts/imports/${jobId}/errors`, {}, token);
}

export async function parseCsvPreview(file: File): Promise<{
    headers: string[];
    rows: string[][];
    totalRows: number;
}> {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = (e) => {
            try {
                const text = e.target?.result as string;
                const lines = text.split("\n").filter((line) => line.trim());
                if (lines.length === 0) {
                    reject(new Error("CSV file is empty"));
                    return;
                }
                const headers = parseCSVLine(lines[0]);
                const rows = lines.slice(1, 11).map((line) => parseCSVLine(line));
                const totalRows = lines.length - 1;
                resolve({ headers, rows, totalRows });
            } catch (err) {
                reject(new Error("Failed to parse CSV file"));
            }
        };
        reader.onerror = () => reject(new Error("Failed to read file"));
        reader.readAsText(file);
    });
}

function parseCSVLine(line: string): string[] {
    const result: string[] = [];
    let current = "";
    let inQuotes = false;
    for (let i = 0; i < line.length; i++) {
        const char = line[i];
        if (char === '"') {
            inQuotes = !inQuotes;
        } else if (char === "," && !inQuotes) {
            result.push(current.trim());
            current = "";
        } else {
            current += char;
        }
    }
    result.push(current.trim());
    return result;
}

export function validateCsvMapping(
    headers: string[],
    mapping: { name: string | null; phone: string | null; tags: string | null }
): { valid: boolean; missing: string[] } {
    const missing: string[] = [];
    if (!mapping.name) missing.push("name");
    if (!mapping.phone) missing.push("phone");
    return { valid: missing.length === 0, missing };
}

export function autoDetectMapping(headers: string[]): {
    name: string | null;
    phone: string | null;
    tags: string | null;
} {
    const lowerHeaders = headers.map((h) => h.toLowerCase());
    return {
        name: headers.find((h) => h.toLowerCase() === "name") || null,
        phone: headers.find((h) => ["phone", "tel", "telephone", "mobile"].includes(h.toLowerCase())) || null,
        tags: headers.find((h) => ["tags", "tag", "labels", "label", "categories", "category"].includes(h.toLowerCase())) || null,
    };
}